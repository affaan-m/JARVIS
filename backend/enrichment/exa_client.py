from __future__ import annotations

from config import Settings


class ExaEnrichmentClient:
    """Small seam for future Exa integration work."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.exa_api_key)

    def build_person_query(self, name: str, company: str | None = None) -> str:
        if company:
            return f'"{name}" "{company}"'
        return f'"{name}"'
