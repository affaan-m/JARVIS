from __future__ import annotations

from pydantic import BaseModel, Field


class EnrichmentRequest(BaseModel):
    """Input payload for an enrichment lookup."""

    name: str
    company: str | None = None
    additional_context: str | None = None


class EnrichmentHit(BaseModel):
    """A single enrichment result from a search."""

    title: str
    url: str
    snippet: str | None = None
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "exa"


class EnrichmentResult(BaseModel):
    """Aggregated enrichment response."""

    query: str
    hits: list[EnrichmentHit] = Field(default_factory=list)
    success: bool = True
    error: str | None = None
