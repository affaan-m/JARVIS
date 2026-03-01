# RESEARCH: Checked Nix4444/Pimeyes-scraper (Selenium-based, XPath scraping)
# DECISION: Direct PimEyes API — fast (~3-8s), no browser needed, uses session cookies
# ALT: Browser Use cloud (too slow, unreliable with PimEyes' custom dropzone UI)
# NOTE: Cookies expire periodically — refresh from Chrome or Cookie-Editor extension
from __future__ import annotations

import asyncio
import base64
import json
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from loguru import logger
from PIL import Image

from config import Settings
from identification.models import FaceSearchMatch, FaceSearchRequest, FaceSearchResult

_BASE_URL = "https://pimeyes.com"
_HEADERS = {
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "https://pimeyes.com",
    "Referer": "https://pimeyes.com/en",
}
_COOKIES_FILE = Path(__file__).parent / "pimeyes_cookies.json"


class PimEyesSearcher:
    """Face searcher using PimEyes direct API (no browser automation).

    Flow: load cookies → upload base64 image → get face IDs →
    start premium search → fetch results → resolve redirect URLs →
    extract person names from source domains.
    ~3-8s per search, zero Browser Use spend.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cookies: dict[str, str] | None = None

    @property
    def configured(self) -> bool:
        return _COOKIES_FILE.exists() or bool(
            self._settings.pimeyes_email and self._settings.pimeyes_password
        )

    def _load_cookies(self) -> dict[str, str]:
        if self._cookies is not None:
            return self._cookies

        if _COOKIES_FILE.exists():
            with open(_COOKIES_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                self._cookies = {c["name"]: c["value"] for c in data}
            else:
                self._cookies = data
            logger.info("PimEyes: loaded {} cookies from {}", len(self._cookies), _COOKIES_FILE.name)
            return self._cookies

        logger.warning("PimEyes: no cookies file at {}", _COOKIES_FILE)
        self._cookies = {}
        return self._cookies

    async def search_face(self, request: FaceSearchRequest) -> FaceSearchResult:
        """Upload a face image to PimEyes and retrieve matching URLs."""
        if not request.image_data:
            return FaceSearchResult(
                success=False,
                error="PimEyes requires image_data (not just embeddings)",
            )

        try:
            return await self._search_via_api(request.image_data)
        except Exception as exc:
            logger.error("PimEyes API search failed: {}", exc)
            return FaceSearchResult(success=False, error=f"PimEyes error: {exc}")

    async def _search_via_api(self, image_data: bytes) -> FaceSearchResult:
        """Direct PimEyes API: upload → search → fetch results → resolve URLs."""
        cookies = self._load_cookies()
        if not cookies:
            return FaceSearchResult(success=False, error="No PimEyes cookies configured")

        # Ensure image is upright (glasses stream can produce sideways frames)
        image_data = self._ensure_upright(image_data)
        logger.info("PimEyes API: starting search, image size={}KB", len(image_data) // 1024)

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            cookies=cookies,
            headers=_HEADERS,
            follow_redirects=True,
        ) as client:
            # Step 1: Check account status
            try:
                status_resp = await client.get(f"{_BASE_URL}/api/premium-token/status")
                if status_resp.status_code == 200:
                    status = status_resp.json()
                    logger.info(
                        "PimEyes: account={} searches={}/{}",
                        status.get("access_type", "?"),
                        status.get("daily_search", "?"),
                        status.get("daily_search_limit", "?"),
                    )
                    if status.get("search_blocked"):
                        return FaceSearchResult(
                            success=False, error="PimEyes account search blocked"
                        )
                else:
                    logger.warning("PimEyes: account check returned {}", status_resp.status_code)
            except Exception as exc:
                logger.warning("PimEyes: account check failed: {}", exc)

            # Step 2: Upload image as base64 data URL
            b64 = base64.b64encode(image_data).decode()
            data_url = f"data:image/jpeg;base64,{b64}"

            upload_resp = await client.post(
                f"{_BASE_URL}/api/upload/file",
                json={"image": data_url},
            )
            if upload_resp.status_code != 200:
                return FaceSearchResult(
                    success=False,
                    error=f"PimEyes upload failed: HTTP {upload_resp.status_code} — {upload_resp.text[:200]}",
                )

            upload_data = upload_resp.json()
            faces = upload_data.get("faces", [])
            if not faces:
                logger.info("PimEyes: no faces detected in uploaded image")
                return FaceSearchResult(
                    success=False, error="PimEyes detected no faces in the image"
                )

            face_ids = [f["id"] for f in faces]
            logger.info("PimEyes: detected {} face(s): {}", len(faces), face_ids)

            # Step 3: Start premium search
            search_resp = await client.post(
                f"{_BASE_URL}/api/search/new",
                json={
                    "faces": face_ids,
                    "type": "PREMIUM_SEARCH",
                    "time": "any",
                    "safeSearch": False,
                    "deepSearch": False,
                    "groups": True,
                    "order": "default",
                },
            )
            if search_resp.status_code != 200:
                return FaceSearchResult(
                    success=False,
                    error=f"PimEyes search start failed: HTTP {search_resp.status_code}",
                )

            search_data = search_resp.json()
            search_hash = search_data.get("searchHash", "")
            api_url = search_data.get("apiUrl", "")

            if not search_hash or not api_url:
                return FaceSearchResult(
                    success=False,
                    error=f"PimEyes returned no searchHash/apiUrl: {search_data}",
                )

            logger.info("PimEyes: search started, hash={}, apiUrl={}", search_hash[:16], api_url[:60])

            # Step 4: Fetch results from external results API (no auth needed)
            results = await self._fetch_results(api_url, search_hash, limit=50)
            logger.info("PimEyes: fetched {} raw results", len(results))

            if not results:
                return FaceSearchResult(
                    success=False, error="PimEyes search returned no results"
                )

            # Step 5: Resolve redirect URLs + build matches (top 20)
            matches = await self._resolve_and_build_matches(results[:20])
            logger.info("PimEyes: built {} matches after URL resolution", len(matches))

            if matches:
                return FaceSearchResult(matches=matches, success=True)

            return FaceSearchResult(
                success=False, error="PimEyes returned results but no usable URLs"
            )

    async def _fetch_results(
        self, api_url: str, search_hash: str, limit: int = 50
    ) -> list[dict]:
        """Fetch paginated results from PimEyes' external results server.

        PimEyes processes searches asynchronously — the first poll may
        return 0 results if the backend hasn't finished.  We retry up to
        5 times with exponential backoff before giving up.
        """
        all_results: list[dict] = []
        max_retries = 5

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20.0), follow_redirects=True
        ) as client:
            # Retry loop: wait for results to become available
            for attempt in range(max_retries):
                if attempt > 0:
                    wait = 1.0 * (1.5 ** (attempt - 1))  # 1s, 1.5s, 2.25s, 3.4s
                    logger.info("PimEyes: results not ready, retry {} in {:.1f}s", attempt, wait)
                    await asyncio.sleep(wait)

                resp = await client.post(
                    api_url,
                    json={"hash": search_hash, "offset": 0, "limit": limit},
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    logger.warning(
                        "PimEyes results fetch returned {}: {}",
                        resp.status_code, resp.text[:200],
                    )
                    continue

                data = resp.json()
                results = data.get("results", [])
                if results:
                    all_results.extend(results)
                    # Fetch additional pages if available
                    offset = len(results)
                    while data.get("isMoreResults", False) and len(all_results) < limit:
                        await asyncio.sleep(0.2)
                        page_resp = await client.post(
                            api_url,
                            json={"hash": search_hash, "offset": offset, "limit": 50},
                            headers={"Content-Type": "application/json"},
                        )
                        if page_resp.status_code != 200:
                            break
                        data = page_resp.json()
                        page_results = data.get("results", [])
                        if not page_results:
                            break
                        all_results.extend(page_results)
                        offset += len(page_results)
                    break  # Got results, stop retrying

        return all_results

    async def _resolve_and_build_matches(
        self, results: list[dict]
    ) -> list[FaceSearchMatch]:
        """Resolve PimEyes proxy URLs and extract person names."""
        matches: list[FaceSearchMatch] = []

        # Resolve URLs concurrently (up to 10 at a time)
        semaphore = asyncio.Semaphore(10)

        async def resolve_one(result: dict) -> FaceSearchMatch | None:
            source_url = result.get("sourceUrl", "")
            thumbnail_url = result.get("thumbnailUrl") or result.get("imageUrl")
            quality = float(result.get("quality", 0))
            domain = result.get("domain", "")

            # Normalize quality to 0-1 range
            similarity = quality / 100.0 if quality > 1.0 else quality
            similarity = max(0.0, min(1.0, similarity))

            # Resolve proxy URL to real destination
            real_url = source_url
            if source_url:
                async with semaphore:
                    real_url = await self._resolve_redirect(source_url)

            if not real_url:
                return None

            # Extract person name from URL/domain
            person_name = self._extract_name_from_url(real_url, domain)

            return FaceSearchMatch(
                url=real_url,
                thumbnail_url=thumbnail_url,
                similarity=similarity,
                source="pimeyes",
                person_name=person_name,
            )

        tasks = [resolve_one(r) for r in results]
        resolved = await asyncio.gather(*tasks, return_exceptions=True)

        for item in resolved:
            if isinstance(item, FaceSearchMatch):
                matches.append(item)
            elif isinstance(item, Exception):
                logger.debug("URL resolve failed: {}", item)

        return matches

    @staticmethod
    async def _resolve_redirect(url: str) -> str:
        """Follow a PimEyes redirect/proxy URL to get the real destination."""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10.0), follow_redirects=True
            ) as client:
                resp = await client.head(url)
                return str(resp.url)
        except Exception:
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(10.0), follow_redirects=True
                ) as client:
                    resp = await client.get(url)
                    return str(resp.url)
            except Exception:
                return url

    @staticmethod
    def _extract_name_from_url(url: str, domain: str) -> str | None:
        """Try to extract a person name from the resolved URL."""
        parsed = urlparse(url)
        path = parsed.path.strip("/")

        # LinkedIn: /in/john-doe → "John Doe"
        if "linkedin.com" in url:
            match = re.search(r"/in/([^/?]+)", path)
            if match:
                slug = match.group(1)
                name = slug.replace("-", " ").title()
                # Filter out generic slugs
                if len(name) > 3 and not name.startswith("Http"):
                    return name

        # Twitter/X: /username → not a name usually, skip
        # Instagram: /username → not a name usually, skip
        # Facebook: /people/John-Doe or /john.doe
        if "facebook.com" in url:
            match = re.search(r"/people/([^/?]+)", path)
            if match:
                return match.group(1).replace("-", " ").title()
            # Profile path like /john.doe
            parts = path.split("/")
            if len(parts) == 1 and "." in parts[0]:
                return parts[0].replace(".", " ").title()

        return None

    @staticmethod
    def _ensure_upright(image_data: bytes) -> bytes:
        """Rotate image to portrait if it appears sideways.

        Meta Ray-Ban glasses stream landscape frames that PimEyes can't
        process. If the image is landscape (wider than tall), rotate 90° CCW
        so faces appear upright.
        """
        try:
            img = Image.open(BytesIO(image_data))
            w, h = img.size
            logger.info("PimEyes: image dimensions {}x{} (landscape={})", w, h, w > h)
            if w > h:
                img = img.rotate(90, expand=True)
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=90)
                rotated = buf.getvalue()
                logger.info(
                    "PimEyes: rotated image {}x{} → {}x{}",
                    w, h, img.size[0], img.size[1],
                )
                return rotated
        except Exception as exc:
            logger.debug("PimEyes: rotation check failed: {}", exc)
        return image_data
