from __future__ import annotations

from typing import Protocol

from synthesis.models import SynthesisRequest, SynthesisResult


class ReportSynthesizer(Protocol):
    """Contract for generating person intelligence reports."""

    @property
    def configured(self) -> bool: ...

    async def synthesize(self, request: SynthesisRequest) -> SynthesisResult:
        """Synthesize enrichment data into a structured person report."""
        ...
