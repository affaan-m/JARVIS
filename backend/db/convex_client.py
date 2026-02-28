from __future__ import annotations

from config import Settings


class ConvexGateway:
    """Thin settings-aware placeholder until the real Convex client is linked."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.convex_url)
