# RESEARCH: Browser Use Cloud API v4 (docs.browser-use.com/cloud/api-v4)
# DECISION: Using httpx async client — pure REST, no SDK needed
# ALT: browser-use pip package (not needed for Cloud API)

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger

from config import Settings

BU_BASE = "https://api.browser-use.com/api/v4"
MAX_RUN_COST_USD = 0.25


class BrowserUseError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"Browser Use API {status_code}: {message}")


class BrowserUseClient:
    """Async client for the Browser Use Cloud V4 run API."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._key = settings.browser_use_api_key
        self._headers = {"X-Browser-Use-API-Key": self._key or ""}
        self._transport = transport

    def _check(self, resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code >= 400:
            logger.error("Browser Use API error: {} {}", resp.status_code, resp.text[:200])
            raise BrowserUseError(resp.status_code, resp.text[:200])
        try:
            return resp.json()
        except ValueError as exc:
            raise BrowserUseError(resp.status_code, "invalid JSON response") from exc

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
                response = await client.request(
                    method,
                    f"{BU_BASE}{path}",
                    headers=self._headers,
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            logger.error("Browser Use API request failed: {}", type(exc).__name__)
            raise BrowserUseError(0, f"request failed: {type(exc).__name__}") from exc
        return self._check(response)

    async def create_run(
        self,
        task: str,
        start_url: str | None = None,
        allowed_domains: list[str] | None = None,
        width: int = 1280,
        height: int = 800,
    ) -> dict[str, Any]:
        """Create a V4 run, which implicitly creates its browser session."""
        instructions: list[str] = []
        if start_url:
            instructions.append(f"Open {start_url} first.")
        if allowed_domains:
            instructions.append(f"Only visit these domains: {', '.join(allowed_domains)}.")
        run_task = "\n".join([*instructions, task])

        body: dict[str, Any] = {
            "task": run_task,
            "browserSettings": {
                "screenWidth": width,
                "screenHeight": height,
                "record": True,
            },
            "maxCostUsd": MAX_RUN_COST_USD,
        }
        result = await self._request("POST", "/runs", json=body)
        logger.info(
            "Created BU V4 run {} in session {}",
            result.get("id"),
            result.get("sessionId"),
        )
        return result

    async def get_session(self, session_id: str) -> dict[str, Any]:
        """Get V4 metadata for a session and its latest run."""
        return await self._request("GET", f"/sessions/{session_id}")

    async def get_run(self, run_id: str) -> dict[str, Any]:
        """Get the full V4 run, including its final result or error."""
        return await self._request("GET", f"/runs/{run_id}")

    async def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        """Get V4 run events used to discover the current live browser URL."""
        result = await self._request(
            "GET",
            f"/runs/{run_id}/events",
            params={"include_output": "false"},
        )
        return result.get("events", [])

    async def make_session_public(self, session_id: str) -> dict[str, Any]:
        """Enable the V4 session's public, read-only replay link."""
        result = await self._request("POST", f"/sessions/{session_id}/share")
        logger.info("Public share created for V4 session {}", session_id)
        return result
