# RESEARCH: Checked supermemory PyPI SDK (official, maintained, wraps REST API)
# DECISION: Using httpx directly per project requirements — thin wrapper around
#   SuperMemory REST API v3/v4 endpoints. SDK exists (`pip install supermemory`)
#   but httpx keeps the dependency surface minimal and gives full control.
# ALT: supermemory Python SDK (official) if we need richer features later.

from __future__ import annotations

import json
import os
from typing import Any

import httpx
from loguru import logger

_BASE_V3 = "https://api.supermemory.ai/v3"
_BASE_V4 = "https://api.supermemory.ai/v4"

# Container tag used to namespace all JARVIS dossiers in SuperMemory.
_CONTAINER_TAG = "jarvis-dossiers"

# Default timeout for SuperMemory API calls (seconds).
_TIMEOUT = 30


class SuperMemoryClient:
    """Async client for SuperMemory REST API.

    Stores and retrieves person dossiers as memories, enabling the pipeline
    to skip redundant enrichment when a person has already been researched.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("SUPERMEMORY_API_KEY", "")
        if not self._api_key:
            logger.warning("SUPERMEMORY_API_KEY not set -- SuperMemory calls will fail")
        self._client = httpx.AsyncClient(
            timeout=_TIMEOUT,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store_dossier(
        self,
        person_name: str,
        dossier_data: dict[str, Any],
    ) -> str | None:
        """Persist a dossier to SuperMemory.

        Returns the document id on success, or None on failure.
        """
        content = json.dumps(
            {"person_name": person_name, "dossier": dossier_data},
            default=str,
        )
        payload: dict[str, Any] = {
            "content": content,
            "containerTags": [_CONTAINER_TAG],
            "customId": _custom_id(person_name),
            "metadata": {
                "person_name": person_name,
                "source": "jarvis-pipeline",
            },
        }
        try:
            resp = await self._client.post(f"{_BASE_V3}/documents", json=payload)
            resp.raise_for_status()
            data = resp.json()
            doc_id = data.get("id")
            logger.info("SuperMemory store OK | person={} id={}", person_name, doc_id)
            return doc_id
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SuperMemory store HTTP {} | person={} body={}",
                exc.response.status_code,
                person_name,
                exc.response.text[:300],
            )
            return None
        except Exception as exc:
            logger.error("SuperMemory store failed | person={} err={}", person_name, exc)
            return None

    async def search_person(self, name: str) -> dict[str, Any] | None:
        """Look up a cached dossier by person name.

        Returns the parsed dossier dict if a high-confidence match is found,
        otherwise None.
        """
        payload: dict[str, Any] = {
            "q": name,
            "containerTag": _CONTAINER_TAG,
            "searchMode": "hybrid",
            "limit": 3,
            "threshold": 0.6,
            "filters": {
                "AND": [
                    {"key": "source", "value": "jarvis-pipeline"},
                ],
            },
        }
        try:
            resp = await self._client.post(f"{_BASE_V4}/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if not results:
                logger.debug("SuperMemory search miss | name={}", name)
                return None

            top = results[0]
            raw = top.get("memory") or top.get("chunk") or ""
            dossier = _parse_dossier(raw, name)
            if dossier is not None:
                logger.info(
                    "SuperMemory cache hit | name={} similarity={:.2f}",
                    name,
                    top.get("similarity", 0),
                )
            return dossier
        except httpx.HTTPStatusError as exc:
            logger.error(
                "SuperMemory search HTTP {} | name={} body={}",
                exc.response.status_code,
                name,
                exc.response.text[:300],
            )
            return None
        except Exception as exc:
            logger.error("SuperMemory search failed | name={} err={}", name, exc)
            return None

    async def close(self) -> None:
        await self._client.aclose()

    # Allow use as async context manager.
    async def __aenter__(self) -> SuperMemoryClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _custom_id(person_name: str) -> str:
    """Deterministic document id so re-storing the same person overwrites."""
    return f"jarvis-{person_name.strip().lower().replace(' ', '-')}"


def _parse_dossier(raw: str, name: str) -> dict[str, Any] | None:
    """Attempt to extract the dossier dict from a SuperMemory memory/chunk."""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "dossier" in obj:
            return obj["dossier"]
        # Might be the dossier itself at top level.
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    # SuperMemory may return a summarised text memory rather than raw JSON.
    # In that case we still return it wrapped as a dict so the caller has
    # something usable.
    if raw and name.lower() in raw.lower():
        return {"raw_memory": raw}
    return None
