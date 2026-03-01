# RESEARCH: Checked convex PyPI (no official Python SDK), httpx for HTTP calls
# DECISION: Using httpx to call Convex HTTP API directly — no SDK needed
# ALT: requests (sync only), aiohttp (heavier dep)

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from config import Settings

_TIMEOUT = 30.0


class ConvexGateway:
    """Convex HTTP API gateway.

    Calls Convex mutation/query functions via the HTTP API documented at
    https://docs.convex.dev/http-api/.

    Implements the DatabaseGateway protocol from db/__init__.py.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._settings.convex_url)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._client

    @property
    def _base_url(self) -> str:
        url = (self._settings.convex_url or "").rstrip("/")
        return url

    async def _mutation(self, fn: str, args: dict[str, Any]) -> Any:
        client = self._get_client()
        url = f"{self._base_url}/api/mutation"
        payload = {"path": fn, "args": args, "format": "json"}
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") == "error":
            raise RuntimeError(f"Convex mutation {fn} failed: {body.get('errorMessage')}")
        return body.get("value")

    async def _query(self, fn: str, args: dict[str, Any]) -> Any:
        client = self._get_client()
        url = f"{self._base_url}/api/query"
        payload = {"path": fn, "args": args, "format": "json"}
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") == "error":
            raise RuntimeError(f"Convex query {fn} failed: {body.get('errorMessage')}")
        return body.get("value")

    async def store_person(self, person_id: str, data: dict[str, Any]) -> str:
        logger.info("ConvexGateway.store_person person_id={}", person_id)
        if not self.configured:
            raise RuntimeError("Convex is not configured (CONVEX_URL missing)")

        # Strip embedding (too large for Convex doc), store as metadata
        safe_data = {k: v for k, v in data.items() if k != "embedding"}
        safe_data["person_id"] = person_id

        try:
            result = await self._mutation("persons:store", {"data": safe_data})
            return result if isinstance(result, str) else person_id
        except Exception as exc:
            logger.error("Convex store_person failed: {}", exc)
            raise

    async def get_person(self, person_id: str) -> dict[str, Any] | None:
        logger.info("ConvexGateway.get_person person_id={}", person_id)
        if not self.configured:
            raise RuntimeError("Convex is not configured (CONVEX_URL missing)")

        try:
            result = await self._query("persons:get", {"person_id": person_id})
            return result
        except Exception as exc:
            logger.error("Convex get_person failed: {}", exc)
            raise

    async def update_person(self, person_id: str, data: dict[str, Any]) -> None:
        logger.info("ConvexGateway.update_person person_id={}", person_id)
        if not self.configured:
            raise RuntimeError("Convex is not configured (CONVEX_URL missing)")

        safe_data = {k: v for k, v in data.items() if k != "embedding"}

        try:
            await self._mutation("persons:update", {
                "person_id": person_id,
                "data": safe_data,
            })
        except Exception as exc:
            logger.error("Convex update_person failed: {}", exc)
            raise

    async def store_capture(self, capture_id: str, metadata: dict[str, Any]) -> str:
        logger.info("ConvexGateway.store_capture capture_id={}", capture_id)
        if not self.configured:
            raise RuntimeError("Convex is not configured (CONVEX_URL missing)")

        safe_metadata = {**metadata, "capture_id": capture_id}

        try:
            result = await self._mutation("captures:store", {"data": safe_metadata})
            return result if isinstance(result, str) else capture_id
        except Exception as exc:
            logger.error("Convex store_capture failed: {}", exc)
            raise

    async def list_persons_with_dossiers(self) -> list[dict[str, Any]]:
        logger.info("ConvexGateway.list_persons_with_dossiers")
        if not self.configured:
            raise RuntimeError("Convex is not configured (CONVEX_URL missing)")

        try:
            result = await self._query("persons:listAll", {})
            if not isinstance(result, list):
                return []
            return [
                p for p in result
                if isinstance(p, dict) and p.get("dossier") is not None
            ]
        except Exception as exc:
            logger.error("Convex list_persons_with_dossiers failed: {}", exc)
            raise

    async def store_intel_fragment(
        self,
        person_id: str,
        source: str,
        content: str,
        *,
        urls: list[str] | None = None,
        confidence: float = 1.0,
        data_type: str = "profile",
    ) -> str | None:
        """Push a single intel fragment to Convex for real-time frontend updates."""
        if not self.configured:
            return None

        # Embed urls + confidence into the content JSON for frontend use
        import json
        content_payload = json.dumps({
            "text": content,
            "urls": urls or [],
            "confidence": confidence,
        })

        try:
            result = await self._mutation("intel:create", {
                "personId": person_id,
                "source": source,
                "dataType": data_type,
                "content": content_payload,
            })
            return result if isinstance(result, str) else None
        except Exception as exc:
            logger.warning("Convex store_intel_fragment failed: {}", exc)
            return None

    async def create_connection(
        self,
        person_a_id: str,
        person_b_id: str,
        relationship_type: str,
        description: str,
    ) -> str:
        logger.info(
            "ConvexGateway.create_connection a={} b={} type={}",
            person_a_id, person_b_id, relationship_type,
        )
        if not self.configured:
            raise RuntimeError("Convex is not configured (CONVEX_URL missing)")

        try:
            result = await self._mutation("connections:create", {
                "personAId": person_a_id,
                "personBId": person_b_id,
                "relationshipType": relationship_type,
                "description": description,
            })
            return result if isinstance(result, str) else ""
        except Exception as exc:
            logger.error("Convex create_connection failed: {}", exc)
            raise
