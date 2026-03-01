"""Environment validation for service adapters.

Checks that required environment variables are set for each service
and reports which services are ready vs. missing configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

from config import Settings


@dataclass(frozen=True)
class ServiceCheck:
    name: str
    ready: bool
    missing_vars: list[str]


_SERVICE_ENV_MAP: dict[str, list[str]] = {
    "convex": ["CONVEX_URL"],
    "exa": ["EXA_API_KEY"],
    "laminar": ["LAMINAR_API_KEY"],
    "gemini": ["GEMINI_API_KEY"],
    "browser_use": ["BROWSER_USE_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "mongodb": ["MONGODB_URI"],
    "telegram": ["TELEGRAM_BOT_TOKEN"],
}


def check_service(name: str, settings: Settings) -> ServiceCheck:
    """Validate a single service's required environment variables."""
    required = _SERVICE_ENV_MAP.get(name, [])
    flags = settings.service_flags()
    missing = [var for var in required if not flags.get(name, False)]
    return ServiceCheck(name=name, ready=len(missing) == 0, missing_vars=missing)


def check_all_services(settings: Settings) -> list[ServiceCheck]:
    """Validate all known services and return their status."""
    return [check_service(name, settings) for name in _SERVICE_ENV_MAP]
