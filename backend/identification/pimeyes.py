# RESEARCH: Checked Nix4444/Pimeyes-scraper (Selenium-based, XPath scraping)
# DECISION: Using httpx + PimEyes undocumented API endpoints instead of Selenium
#   PimEyes has REST-ish endpoints under the hood; avoids heavy browser dependency.
#   Falls back gracefully when API changes or rate-limited (10 searches/IP).
# ALT: Browser Use agent as Tier-2 fallback (see search_manager.py)
from __future__ import annotations

import base64
import json
from typing import Any

import httpx
from loguru import logger

from config import Settings
from identification.models import FaceSearchMatch, FaceSearchRequest, FaceSearchResult

# PimEyes endpoints (reverse-engineered from web client)
_PIMEYES_UPLOAD_URL = "https://pimeyes.com/api/upload/file"
_PIMEYES_SEARCH_URL = "https://pimeyes.com/api/search/new"
_PIMEYES_RESULTS_URL = "https://pimeyes.com/api/search/results"

_DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Origin": "https://pimeyes.com",
    "Referer": "https://pimeyes.com/en",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
}

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class PimEyesSearcher:
    """Face searcher using PimEyes reverse face search.

    Implements the FaceSearcher protocol from identification/__init__.py.
    Uses httpx to hit PimEyes API endpoints directly (no Selenium).
    Supports account pool rotation for rate-limit evasion.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._accounts: list[dict[str, str]] = self._parse_account_pool(
            settings.pimeyes_account_pool
        )

    @property
    def configured(self) -> bool:
        return True  # Works without accounts for free-tier searches

    @staticmethod
    def _parse_account_pool(pool_json: str) -> list[dict[str, str]]:
        try:
            accounts = json.loads(pool_json)
            if isinstance(accounts, list):
                return accounts
        except (json.JSONDecodeError, TypeError):
            pass
        return []

    async def search_face(self, request: FaceSearchRequest) -> FaceSearchResult:
        """Upload a face image to PimEyes and retrieve matching URLs."""
        if not request.image_data:
            return FaceSearchResult(
                success=False,
                error="PimEyes requires image_data (not just embeddings)",
            )

        try:
            return await self._do_search(request.image_data)
        except httpx.TimeoutException:
            logger.warning("PimEyes search timed out")
            return FaceSearchResult(success=False, error="PimEyes request timed out")
        except Exception as exc:
            logger.error("PimEyes search failed: {}", exc)
            return FaceSearchResult(success=False, error=f"PimEyes error: {exc}")

    async def _do_search(self, image_data: bytes) -> FaceSearchResult:
        """Execute the full PimEyes search flow: upload → search → poll results."""
        async with httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers=_DEFAULT_HEADERS,
            follow_redirects=True,
        ) as client:
            # Step 1: Upload face image
            upload_resp = await self._upload_image(client, image_data)
            if not upload_resp:
                return FaceSearchResult(success=False, error="PimEyes upload failed")

            search_id = upload_resp.get("id") or upload_resp.get("searchHash")
            if not search_id:
                logger.warning("PimEyes upload response missing search ID: {}", upload_resp)
                return FaceSearchResult(success=False, error="No search ID in upload response")

            # Step 2: Trigger search
            search_resp = await self._trigger_search(client, search_id)
            if not search_resp:
                return FaceSearchResult(success=False, error="PimEyes search trigger failed")

            # Step 3: Fetch results
            results = await self._fetch_results(client, search_id)
            return self._parse_results(results)

    async def _upload_image(
        self, client: httpx.AsyncClient, image_data: bytes
    ) -> dict[str, Any] | None:
        b64 = base64.b64encode(image_data).decode()
        payload = {"image": f"data:image/jpeg;base64,{b64}"}

        resp = await client.post(_PIMEYES_UPLOAD_URL, json=payload)
        if resp.status_code != 200:
            logger.warning("PimEyes upload returned {}: {}", resp.status_code, resp.text[:200])
            return None

        return resp.json()

    async def _trigger_search(
        self, client: httpx.AsyncClient, search_id: str
    ) -> dict[str, Any] | None:
        payload = {"searchId": search_id, "searchType": "FACE"}
        cookies = self._get_cookies()

        resp = await client.post(_PIMEYES_SEARCH_URL, json=payload, cookies=cookies)
        if resp.status_code != 200:
            logger.warning("PimEyes search trigger returned {}", resp.status_code)
            return None

        return resp.json()

    async def _fetch_results(
        self, client: httpx.AsyncClient, search_id: str
    ) -> list[dict[str, Any]]:
        params = {"searchId": search_id}
        cookies = self._get_cookies()

        resp = await client.get(_PIMEYES_RESULTS_URL, params=params, cookies=cookies)
        if resp.status_code != 200:
            logger.warning("PimEyes results returned {}", resp.status_code)
            return []

        data = resp.json()
        return data.get("results", [])

    def _get_cookies(self) -> dict[str, str]:
        if self._accounts:
            account = self._accounts[0]
            return {k: v for k, v in account.items() if k.startswith("__")}
        return {}

    @staticmethod
    def _parse_results(results: list[dict[str, Any]]) -> FaceSearchResult:
        matches: list[FaceSearchMatch] = []
        for item in results[:20]:  # Cap at 20 results
            url = item.get("sourceUrl") or item.get("url", "")
            thumbnail = item.get("thumbnailUrl") or item.get("thumbnail")
            similarity = float(item.get("similarity", item.get("score", 0.0)))
            # Normalize similarity to 0-1 range
            if similarity > 1.0:
                similarity = similarity / 100.0
            similarity = max(0.0, min(1.0, similarity))

            matches.append(
                FaceSearchMatch(
                    url=url,
                    thumbnail_url=thumbnail,
                    similarity=similarity,
                    source="pimeyes",
                    person_name=item.get("name"),
                )
            )

        logger.info("PimEyes returned {} matches", len(matches))
        return FaceSearchResult(matches=matches, success=True)
