# RESEARCH: Checked litellm Router (key/deployment load balancing, heavy dependency)
#   and openai-key-rotator style gists (tiny, unmaintained).
# DECISION: BUILD — ~60 lines, no new dependency, shared across engine + agents
# ALT: litellm Router if we ever need cross-provider load balancing

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Hashable, Sequence
from typing import Generic, TypeVar

from loguru import logger

T = TypeVar("T", bound=Hashable)


def mask_key(key: str) -> str:
    return f"...{key[-4:]}" if key else "<none>"


def parse_keys(raw: str | None) -> list[str]:
    """Split a comma/newline separated key list, dropping blanks and duplicates."""
    if not raw:
        return []
    keys: list[str] = []
    for part in raw.replace("\n", ",").split(","):
        key = part.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


class KeyPool(Generic[T]):
    """Round-robin pool (API keys, or key/model pairs) that skips items cooling down."""

    def __init__(
        self,
        name: str,
        keys: Sequence[T],
        label: Callable[[T], str] = lambda item: mask_key(str(item)),
    ):
        self.name = name
        self._keys: list[T] = list(keys)
        self._label = label
        self._index = 0
        self._cooldown_until: dict[T, float] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._keys)

    def next_key(self) -> T | None:
        """Return the next available key; if all are cooling down, the one freed soonest."""
        with self._lock:
            if not self._keys:
                return None
            now = time.monotonic()
            for _ in range(len(self._keys)):
                key = self._keys[self._index]
                self._index = (self._index + 1) % len(self._keys)
                if self._cooldown_until.get(key, 0.0) <= now:
                    return key
            return min(self._keys, key=lambda k: self._cooldown_until.get(k, 0.0))

    def mark_failed(self, key: T, cooldown_s: float = 60.0) -> None:
        """Take an item out of rotation for cooldown_s seconds."""
        with self._lock:
            self._cooldown_until[key] = time.monotonic() + cooldown_s
        logger.warning(
            "key_pool={} item={} cooling down {}s", self.name, self._label(key), int(cooldown_s)
        )


_pools: dict[tuple[str, tuple], KeyPool] = {}
_pools_lock = threading.Lock()


def get_pool(name: str, items: Sequence[T], label: Callable[[T], str] | None = None) -> KeyPool[T]:
    """Return the shared pool for these items so all callers rotate together."""
    cache_key = (name, tuple(items))
    with _pools_lock:
        pool = _pools.get(cache_key)
        if pool is None:
            pool = KeyPool(name, items, label) if label else KeyPool(name, items)
            _pools[cache_key] = pool
        return pool


def get_key_model_pool(
    name: str, raw_keys: str | None, models: Sequence[str]
) -> KeyPool[tuple[str, str]]:
    """Shared pool of (key, model) pairs, model-major so load spreads over keys first."""
    pairs = [(key, model) for model in models for key in parse_keys(raw_keys)]
    return get_pool(name, pairs, label=lambda p: f"{mask_key(p[0])}/{p[1]}")


def get_key_pool(name: str, raw_keys: str | None) -> KeyPool[str]:
    """Shared pool for a comma-separated key string."""
    return get_pool(name, parse_keys(raw_keys))
