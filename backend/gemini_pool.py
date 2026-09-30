# RESEARCH: google-genai has no built-in key/model rotation; litellm Router can do
#   it but would replace the google-genai calls wholesale.
# DECISION: BUILD — thin wrapper over key_pool rotating (API key, model) pairs
# ALT: litellm Router with one deployment per key/model

from __future__ import annotations

from typing import Any

from loguru import logger

from key_pool import KeyPool, get_pool, mask_key, parse_keys

DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

# HTTP status -> seconds to take a (key, model) pair out of rotation
_COOLDOWNS: dict[int, float] = {
    429: 60.0,      # quota / rate limit
    401: 3600.0,    # bad key
    403: 3600.0,    # key not allowed for this model/project
    404: 3600.0,    # model not available
    500: 20.0,
    502: 20.0,
    503: 20.0,
    504: 20.0,
}


class GeminiRotator:
    """Round-robin over every (API key, model) pair, skipping pairs that errored."""

    def __init__(self, raw_keys: str | None, raw_models: str | None = None):
        self.keys = parse_keys(raw_keys)
        self.models = parse_keys(raw_models) or [DEFAULT_GEMINI_MODEL]
        # Model-major order: spread load over keys first, then move to the next model
        pairs = [(key, model) for model in self.models for key in self.keys]
        self._pool: KeyPool[tuple[str, str]] = get_pool(
            "gemini", pairs, label=lambda p: f"{mask_key(p[0])}/{p[1]}"
        )
        self._clients: dict[str, Any] = {}
        # Tests may inject a single client used for every key
        self.client_override: Any = None

    @property
    def configured(self) -> bool:
        return len(self._pool) > 0

    def _client_for(self, key: str) -> Any:
        if self.client_override is not None:
            return self.client_override
        if key not in self._clients:
            from google import genai

            self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    def generate_content(self, **kwargs: Any) -> Any:
        """Blocking generate_content with key/model failover. Raises the last error."""
        from google.genai import errors

        last_exc: Exception | None = None
        for _ in range(max(1, len(self._pool))):
            pair = self._pool.next_key()
            if pair is None:
                break
            key, model = pair
            try:
                logger.debug("gemini call key={} model={}", mask_key(key), model)
                return self._client_for(key).models.generate_content(model=model, **kwargs)
            except errors.APIError as exc:
                cooldown = _COOLDOWNS.get(getattr(exc, "code", 0) or 0)
                if cooldown is None:
                    raise
                last_exc = exc
                self._pool.mark_failed(pair, cooldown_s=cooldown)
        if last_exc is None:
            raise RuntimeError("No Gemini API key configured (GEMINI_API_KEY)")
        raise last_exc
