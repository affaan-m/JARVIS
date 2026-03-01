"""Base browser agent wrapper around browser-use with timeout and error handling.

# RESEARCH: Checked browser-use (47k stars, updated Feb 2026, official SDK)
# DECISION: Using browser-use directly — official library, well-maintained, async-native
# ALT: playwright raw (more control, more boilerplate)
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from loguru import logger

from agents.models import AgentResult, AgentStatus, ResearchRequest
from config import Settings
from observability.laminar import traced

DEFAULT_TIMEOUT_SECONDS = 180.0


class BaseBrowserAgent(ABC):
    """Abstract base class for browser-based research agents.

    Handles timeout enforcement, error isolation, structured logging,
    and Browser Use cloud session management with persistent auth.
    """

    agent_name: str = "base"

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(self._settings.browser_use_api_key or self._settings.openai_api_key)

    @abstractmethod
    async def _run_task(self, request: ResearchRequest) -> AgentResult:
        """Subclass-specific research logic. Must return AgentResult."""
        ...

    @traced("agent.run")
    async def run(self, request: ResearchRequest) -> AgentResult:
        """Execute the agent with timeout and error isolation."""
        timeout = request.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        start = time.monotonic()

        logger.info(
            "agent={} status=start person={} timeout={}s",
            self.agent_name,
            request.person_name,
            timeout,
        )

        try:
            result = await asyncio.wait_for(
                self._run_task(request),
                timeout=timeout,
            )
            elapsed = time.monotonic() - start
            result = result.model_copy(
                update={
                    "duration_seconds": elapsed,
                    "completed_at": datetime.now(UTC),
                }
            )
            logger.info(
                "agent={} status={} person={} elapsed={:.1f}s profiles={} snippets={}",
                self.agent_name,
                result.status.value,
                request.person_name,
                elapsed,
                len(result.profiles),
                len(result.snippets),
            )
            return result

        except TimeoutError:
            elapsed = time.monotonic() - start
            logger.warning(
                "agent={} status=timeout person={} elapsed={:.1f}s",
                self.agent_name,
                request.person_name,
                elapsed,
            )
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.TIMEOUT,
                error=f"Agent timed out after {timeout}s",
                duration_seconds=elapsed,
                completed_at=datetime.now(UTC),
            )

        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "agent={} status=failed person={} elapsed={:.1f}s error={}",
                self.agent_name,
                request.person_name,
                elapsed,
                str(exc),
            )
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=str(exc),
                duration_seconds=elapsed,
                completed_at=datetime.now(UTC),
            )

    def _build_search_query(self, request: ResearchRequest) -> str:
        """Build a search query string from the request."""
        parts = [request.person_name]
        if request.company:
            parts.append(request.company)
        return " ".join(parts)

    def _create_browser_agent(self, task: str):
        """Create a Browser Use Agent with cloud session support if BROWSER_USE_API_KEY is set.

        Cloud mode (BROWSER_USE_API_KEY set):
          - Sets BrowserProfile(use_cloud=True) which connects to Browser Use cloud
          - The SDK reads BROWSER_USE_API_KEY from env automatically
          - Cloud sessions persist cookies/auth across runs — log into LinkedIn/Twitter/
            Instagram once via `browseruse` CLI, and sessions reuse those cookies

        Local mode (no BROWSER_USE_API_KEY):
          - Falls back to headless local Chromium via Playwright

        To set up authenticated sessions for cloud mode:
          1. Set BROWSER_USE_API_KEY in your .env
          2. Run `browseruse` CLI interactively
          3. Log into LinkedIn, Twitter, Instagram manually
          4. Sessions persist in your Browser Use cloud profile
          5. All subsequent agent runs reuse those authenticated sessions
        """
        from browser_use import Agent
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=self._settings.openai_api_key,
        )

        agent_kwargs: dict = {"task": task, "llm": llm}

        if self._settings.browser_use_api_key:
            try:
                from browser_use.browser.profile import BrowserProfile

                profile = BrowserProfile(
                    use_cloud=True,
                    headless=True,
                )
                agent_kwargs["browser_profile"] = profile
                logger.debug(
                    "agent={} using Browser Use cloud (BROWSER_USE_API_KEY set)",
                    self.agent_name,
                )
            except Exception as exc:
                logger.warning(
                    "agent={} cloud browser setup failed, using local: {}",
                    self.agent_name,
                    str(exc),
                )
        else:
            logger.debug(
                "agent={} using local browser (no BROWSER_USE_API_KEY)",
                self.agent_name,
            )

        return Agent(**agent_kwargs)
