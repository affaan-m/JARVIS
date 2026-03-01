"""Base browser agent wrapper around browser-use with timeout and error handling.

# RESEARCH: Checked browser-use (47k stars, updated Feb 2026, official SDK v0.12.0)
# DECISION: Using browser-use directly — official library, well-maintained, async-native
# ALT: playwright raw (more control, more boilerplate)
# NOTE: Cloud mode uses Browser(use_cloud=True) + ChatBrowserUse(). SDK reads
#   BROWSER_USE_API_KEY from env automatically. Cloud sessions persist cookies/auth.
"""

from __future__ import annotations

import asyncio
import os
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
        # Ensure BROWSER_USE_API_KEY is in os.environ so the SDK picks it up
        if settings.browser_use_api_key and not os.environ.get("BROWSER_USE_API_KEY"):
            os.environ["BROWSER_USE_API_KEY"] = settings.browser_use_api_key

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

    def _build_llm(self):
        """Build the LLM instance for browser-use agents.

        Prefers ChatBrowserUse (optimized for browser automation, 3-5x faster).
        Falls back to ChatOpenAI with gpt-4o-mini if OPENAI_API_KEY is set.
        """
        # Prefer ChatBrowserUse when we have a Browser Use API key (cloud mode)
        if self._settings.browser_use_api_key:
            try:
                from browser_use import ChatBrowserUse

                logger.debug("agent={} using ChatBrowserUse LLM", self.agent_name)
                return ChatBrowserUse()
            except (ImportError, Exception) as exc:
                logger.debug(
                    "agent={} ChatBrowserUse unavailable ({}), trying ChatOpenAI",
                    self.agent_name,
                    str(exc),
                )

        # Fallback to ChatOpenAI
        if self._settings.openai_api_key:
            from langchain_openai import ChatOpenAI

            logger.debug("agent={} using ChatOpenAI gpt-4o-mini", self.agent_name)
            return ChatOpenAI(
                model="gpt-4o-mini",
                api_key=self._settings.openai_api_key,
            )

        raise RuntimeError("No LLM configured: set BROWSER_USE_API_KEY or OPENAI_API_KEY")

    def _create_browser_agent(self, task: str):
        """Create a Browser Use Agent with cloud or local browser.

        Cloud mode (BROWSER_USE_API_KEY set):
          - Creates Browser(use_cloud=True) for stealth cloud browser with proxy rotation,
            CAPTCHA bypass, and persistent cookie/auth sessions
          - Uses ChatBrowserUse() as the LLM (optimized for browser automation)
          - The SDK reads BROWSER_USE_API_KEY from os.environ automatically

        Local mode (no BROWSER_USE_API_KEY, OPENAI_API_KEY set):
          - Falls back to headless local Chromium via Playwright
          - Uses ChatOpenAI(gpt-4o-mini) as the LLM

        To set up authenticated sessions for cloud mode:
          1. Set BROWSER_USE_API_KEY in your .env
          2. Run: export BROWSER_USE_API_KEY=<key> && curl -fsSL https://browser-use.com/profile.sh | sh
          3. Log into LinkedIn, Twitter, Instagram in the opened browser
          4. Sessions persist in your Browser Use cloud profile
          5. All subsequent agent runs reuse those authenticated sessions
        """
        from browser_use import Agent

        llm = self._build_llm()
        agent_kwargs: dict = {"task": task, "llm": llm}

        if self._settings.browser_use_api_key:
            try:
                from browser_use import Browser

                browser = Browser(use_cloud=True)
                agent_kwargs["browser"] = browser
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
