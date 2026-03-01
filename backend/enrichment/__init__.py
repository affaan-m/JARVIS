from __future__ import annotations

from typing import Protocol

from enrichment.models import EnrichmentRequest, EnrichmentResult


class EnrichmentClient(Protocol):
    """Contract for person enrichment lookups (Exa, etc.)."""

    @property
    def configured(self) -> bool: ...

    async def enrich_person(self, request: EnrichmentRequest) -> EnrichmentResult:
        """Run an enrichment lookup for a person."""
        ...
