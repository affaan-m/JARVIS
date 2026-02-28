from __future__ import annotations

from config import Settings


def laminar_ready(settings: Settings) -> bool:
    return bool(settings.laminar_api_key)
