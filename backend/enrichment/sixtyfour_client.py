# RESEARCH: SixtyFour.ai API — agentic lead enrichment + deep people search
# DECISION: Build thin httpx wrapper. Enrich-lead is fast (~2-5s, structured).
#   Deep search is async (start → poll → download CSV). Run both in parallel with Exa.
# ALT: No existing Python SDK for SixtyFour.ai, must build from scratch.

from __future__ import annotations

import asyncio
import csv
import io
from dataclasses import dataclass, field

import httpx
from loguru import logger

from config import Settings

BASE_URL = "https://api.sixtyfour.ai"
POLL_INTERVAL_S = 3.0
MAX_POLL_ATTEMPTS = 60  # 3min max


@dataclass(frozen=True)
class EnrichResult:
    """Structured lead data from enrich-lead endpoint."""

    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    twitter: str | None = None
    instagram: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None
    findings: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    raw: dict | None = None
    success: bool = True
    error: str | None = None


@dataclass(frozen=True)
class DeepSearchResult:
    """Results from deep search (parsed from downloaded CSV)."""

    task_id: str = ""
    rows: list[dict[str, str]] = field(default_factory=list)
    urls_found: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None


class SixtyFourClient:
    """SixtyFour.ai API client for lead enrichment + deep people search."""

    def __init__(self, settings: Settings):
        self._api_key = settings.sixtyfour_api_key
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"x-api-key": self._api_key or ""},
                timeout=timeout,
            )
        return self._client

    async def enrich_lead(
        self,
        name: str,
        company: str | None = None,
    ) -> EnrichResult:
        """Fast structured lead enrichment (~2-5s).

        Returns structured profile data: name, email, phone, social URLs, etc.
        """
        if not self.configured:
            return EnrichResult(
                success=False, error="SIXTYFOUR_API_KEY not configured"
            )

        client = self._get_client()
        lead_info: dict[str, str] = {"name": name}
        if company:
            lead_info["company"] = company

        payload = {
            "lead_info": lead_info,
            "struct": {
                "name": "string",
                "email": "string",
                "phone": "string",
                "linkedin": "string",
                "github": "string",
                "twitter": "string",
                "instagram": "string",
                "company": "string",
                "title": "string",
                "location": "string",
            },
        }

        try:
            logger.info("sixtyfour: enrich_lead for '{}' (timeout=180s)", name)
            resp = await client.post(
                "/enrich-lead", json=payload,
                timeout=180.0,  # Agentic endpoint — can take 60-120s
            )
            resp.raise_for_status()
            data = resp.json()

            structured = data.get("structured_data", {})
            findings = data.get("findings", [])
            references = data.get("references", [])

            if isinstance(findings, str):
                findings = [findings]
            if isinstance(references, str):
                references = [references]

            result = EnrichResult(
                name=structured.get("name"),
                email=structured.get("email"),
                phone=structured.get("phone"),
                linkedin=structured.get("linkedin"),
                github=structured.get("github"),
                twitter=structured.get("twitter"),
                instagram=structured.get("instagram"),
                company=structured.get("company"),
                title=structured.get("title"),
                location=structured.get("location"),
                findings=findings if isinstance(findings, list) else [],
                references=references if isinstance(references, list) else [],
                raw=data,
            )
            logger.info(
                "sixtyfour: enrich_lead success — email={} linkedin={} findings={}",
                result.email,
                result.linkedin,
                len(result.findings),
            )
            return result

        except httpx.HTTPStatusError as exc:
            logger.error(
                "sixtyfour: enrich_lead HTTP error {}: {}",
                exc.response.status_code,
                exc.response.text[:200],
            )
            return EnrichResult(
                success=False,
                error=f"HTTP {exc.response.status_code}",
            )
        except httpx.TimeoutException as exc:
            logger.error("sixtyfour: enrich_lead TIMEOUT ({}): {}", type(exc).__name__, exc)
            return EnrichResult(success=False, error=f"Timeout: {type(exc).__name__}")
        except Exception as exc:
            logger.error("sixtyfour: enrich_lead error ({}): {}", type(exc).__name__, exc)
            return EnrichResult(success=False, error=str(exc))

    async def start_deep_search(
        self,
        query: str,
        *,
        mode: str = "people",
        max_results: int = 50,
    ) -> str | None:
        """Start an async deep search. Returns task_id or None on failure."""
        if not self.configured:
            return None

        client = self._get_client()
        payload = {
            "query": query,
            "mode": mode,
            "max_results": max_results,
        }

        try:
            logger.info("sixtyfour: starting deep search query='{}'", query)
            resp = await client.post("/search/start-deep-search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("task_id")
            logger.info("sixtyfour: deep search started task_id={}", task_id)
            return task_id
        except Exception as exc:
            logger.error("sixtyfour: start_deep_search error: {}", exc)
            return None

    async def poll_deep_search(self, task_id: str) -> DeepSearchResult:
        """Poll a deep search until completion, then download + parse results."""
        if not self.configured:
            return DeepSearchResult(
                task_id=task_id,
                success=False,
                error="SIXTYFOUR_API_KEY not configured",
            )

        client = self._get_client()

        for attempt in range(MAX_POLL_ATTEMPTS):
            try:
                resp = await client.get(
                    f"/search/deep-search-status/{task_id}"
                )
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status", "")

                if status == "completed":
                    resource_handle_id = data.get("resource_handle_id")
                    if resource_handle_id:
                        return await self._download_results(
                            task_id, resource_handle_id
                        )
                    return DeepSearchResult(
                        task_id=task_id,
                        success=True,
                    )

                if status in ("failed", "error"):
                    return DeepSearchResult(
                        task_id=task_id,
                        success=False,
                        error=f"Deep search failed: {data}",
                    )

                logger.debug(
                    "sixtyfour: deep search {} status={} (attempt {}/{})",
                    task_id,
                    status,
                    attempt + 1,
                    MAX_POLL_ATTEMPTS,
                )
                await asyncio.sleep(POLL_INTERVAL_S)

            except Exception as exc:
                logger.warning(
                    "sixtyfour: poll error for {}: {}", task_id, exc
                )
                await asyncio.sleep(POLL_INTERVAL_S)

        return DeepSearchResult(
            task_id=task_id,
            success=False,
            error=f"Timed out after {MAX_POLL_ATTEMPTS} polls",
        )

    async def _download_results(
        self, task_id: str, resource_handle_id: str
    ) -> DeepSearchResult:
        """Download deep search results CSV and parse into structured data."""
        client = self._get_client()

        try:
            resp = await client.get(
                "/search/download",
                params={"resource_handle_id": resource_handle_id},
            )
            resp.raise_for_status()

            # Response may be a signed URL or direct CSV
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else None  # noqa: E501

            if data and data.get("url"):
                # Download from signed URL
                async with httpx.AsyncClient(timeout=30.0) as dl_client:
                    csv_resp = await dl_client.get(data["url"])
                    csv_resp.raise_for_status()
                    csv_text = csv_resp.text
            else:
                csv_text = resp.text

            # Parse CSV
            rows: list[dict[str, str]] = []
            urls_found: list[str] = []

            reader = csv.DictReader(io.StringIO(csv_text))
            for row in reader:
                rows.append(dict(row))
                # Extract any URL-like fields
                for _key, value in row.items():
                    if value and (
                        value.startswith("http")
                        or "linkedin.com" in value
                        or "twitter.com" in value
                        or "github.com" in value
                    ):
                        urls_found.append(value)

            logger.info(
                "sixtyfour: downloaded {} rows, {} URLs from deep search {}",
                len(rows),
                len(urls_found),
                task_id,
            )

            return DeepSearchResult(
                task_id=task_id,
                rows=rows,
                urls_found=urls_found,
            )

        except Exception as exc:
            logger.error(
                "sixtyfour: download error for {}: {}", task_id, exc
            )
            return DeepSearchResult(
                task_id=task_id,
                success=False,
                error=f"Download failed: {exc}",
            )

    async def find_email(
        self, name: str, company: str | None = None
    ) -> str | None:
        """Find email address for a person. Returns email or None."""
        if not self.configured:
            return None

        client = self._get_client()
        lead: dict[str, str] = {"name": name}
        if company:
            lead["company"] = company

        try:
            resp = await client.post("/find-email", json={"lead": lead})
            resp.raise_for_status()
            data = resp.json()
            email = data.get("email")
            if email:
                logger.info("sixtyfour: found email for '{}': {}", name, email)
            return email
        except Exception as exc:
            logger.error("sixtyfour: find_email error: {}", exc)
            return None

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
