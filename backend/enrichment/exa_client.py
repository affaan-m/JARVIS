from __future__ import annotations

from loguru import logger

from config import Settings
from enrichment.models import EnrichmentHit, EnrichmentRequest, EnrichmentResult


class ExaEnrichmentClient:
    """Exa API client for person enrichment lookups.

    RESEARCH: Checked exa-py (official SDK), tavily-python, serper-dev
    DECISION: Using exa-py — official SDK, neural search, best for person lookups
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._settings.exa_api_key)

    def _get_client(self):
        if self._client is None:
            from exa_py import Exa

            self._client = Exa(api_key=self._settings.exa_api_key)
        return self._client

    def build_person_query(self, name: str, company: str | None = None) -> str:
        if company:
            return f'"{name}" "{company}"'
        return f'"{name}"'

    async def enrich_person(self, request: EnrichmentRequest) -> EnrichmentResult:
        query = self.build_person_query(request.name, request.company)
        logger.info("ExaEnrichmentClient.enrich_person query={}", query)

        if not self.configured:
            return EnrichmentResult(
                query=query,
                success=False,
                error="Exa API key not configured (EXA_API_KEY missing)",
            )

        try:
            exa = self._get_client()
            search_query = f"{request.name}"
            if request.company:
                search_query += f" {request.company}"
            if request.additional_context:
                search_query += f" {request.additional_context}"

            response = exa.search_and_contents(
                search_query,
                type="auto",
                num_results=10,
                text={"max_characters": 1000},
                highlights=True,
            )

            hits: list[EnrichmentHit] = []
            for result in response.results:
                snippet = ""
                if hasattr(result, "highlights") and result.highlights:
                    snippet = " ... ".join(result.highlights[:3])
                elif hasattr(result, "text") and result.text:
                    snippet = result.text[:500]

                score = result.score if hasattr(result, "score") and result.score else 0.5
                score = max(0.0, min(1.0, score))

                hits.append(
                    EnrichmentHit(
                        title=result.title or "",
                        url=result.url or "",
                        snippet=snippet or None,
                        score=score,
                        source="exa",
                    )
                )

            logger.info("Exa returned {} hits for query={}", len(hits), query)
            return EnrichmentResult(query=query, hits=hits)

        except Exception as e:
            logger.error("Exa API call failed: {}", e)
            return EnrichmentResult(
                query=query,
                success=False,
                error=f"Exa API error: {e}",
            )
