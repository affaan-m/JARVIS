"""Base browser agent wrapper around browser-use with timeout and error handling.

# RESEARCH: Checked browser-use (47k stars, updated Feb 2026, SDK v0.12.0, BU 2.0 model)
# DECISION: Using browser-use directly with BU 2.0 model (+12% accuracy over 1.0)
# ALT: v3 SDK experimental API (too new, may break)
# NOTE: Cloud mode uses Browser(use_cloud=True) + ChatBrowserUse(model="bu-2-0").
#   SDK reads BROWSER_USE_API_KEY from env automatically.
#   Cloud sessions persist cookies/auth for authenticated platform access.
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

DEFAULT_TIMEOUT_SECONDS = 90.0
SIGNUP_PASSWORD = "Jarvis2026!"


class BaseBrowserAgent(ABC):
    """Abstract base class for browser-based research agents.

    Handles timeout enforcement, error isolation, structured logging,
    and Browser Use cloud session management with persistent auth.
    AgentMail integration provides disposable signup emails as fallback
    when agents hit login walls. Supports shared InboxPool for zero-latency
    email acquisition across parallel agents.
    """

    agent_name: str = "base"

    def __init__(self, settings: Settings, *, inbox_pool=None):
        self._settings = settings
        self._agentmail = None  # lazy-init
        self._inbox_pool = inbox_pool  # shared pool from orchestrator
        self._signup_email: str | None = None
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

    def _get_agentmail(self):
        """Lazy-init AgentMailClient. Returns None if API key not set."""
        if self._agentmail is not None:
            return self._agentmail

        if not self._settings.agentmail_api_key:
            return None

        try:
            from agents.agentmail_client import AgentMailClient

            self._agentmail = AgentMailClient(api_key=self._settings.agentmail_api_key)
            if self._agentmail.configured:
                logger.debug("agent={} agentmail client ready", self.agent_name)
                return self._agentmail
            self._agentmail = None
        except Exception as exc:
            logger.warning("agent={} agentmail init failed: {}", self.agent_name, exc)
            self._agentmail = None

        return None

    def _get_signup_email(self) -> str | None:
        """Get a disposable email for signup fallback.

        Tries the shared InboxPool first (zero latency if pre-warmed),
        falls back to creating on-demand via AgentMailClient.
        Caches the email so repeated calls return the same inbox.
        """
        if self._signup_email:
            return self._signup_email

        # Try shared pool first (pre-warmed, instant)
        if self._inbox_pool is not None:
            email = self._inbox_pool.acquire(self.agent_name)
            if email:
                self._signup_email = email
                logger.info("agent={} signup_email={} (from pool)", self.agent_name, email)
                return email

        # Fallback to on-demand creation
        client = self._get_agentmail()
        if client is None:
            return None

        try:
            inbox = client.create_inbox(label=f"jarvis-{self.agent_name}")
            self._signup_email = inbox["email"]
            logger.info("agent={} signup_email={} (on-demand)", self.agent_name, self._signup_email)
            return self._signup_email
        except Exception as exc:
            logger.warning("agent={} failed to create signup inbox: {}", self.agent_name, exc)
            return None

    def _login_wall_fallback_instruction(self) -> str:
        """Return a task instruction snippet for login-wall bypass via AgentMail signup.

        Returns empty string if AgentMail is not configured (no-op in prompt).
        Does NOT eagerly acquire an inbox -- that happens lazily in _create_browser_agent.
        """
        has_agentmail = bool(
            (self._inbox_pool is not None)
            or self._settings.agentmail_api_key
        )
        if not has_agentmail:
            return ""
        return (
            "\n\nIMPORTANT: If you are blocked by a login wall or sign-up screen, "
            "create a new account using email {signup_email} with password "
            "{signup_password}. After signing up, check for a verification email "
            "and complete the verification if required, then continue with the task."
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
        # Prefer ChatBrowserUse with BU 2.0 model (+12% accuracy over 1.0)
        if self._settings.browser_use_api_key:
            try:
                from browser_use import ChatBrowserUse

                logger.debug("agent={} using ChatBrowserUse bu-2-0", self.agent_name)
                return ChatBrowserUse(model="bu-2-0")
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

    def _create_browser_agent(
        self, task: str, *, max_steps: int = 10, needs_login: bool = False,
    ):
        """Create a Browser Use Agent optimized for speed.

        Speed optimizations:
          - flash_mode=True for faster LLM responses
          - max_failures=2 to fail fast instead of retrying 5x
          - enable_planning=False to skip planning overhead on focused tasks
          - step_timeout=60 to kill stuck navigation steps quickly
          - max_actions_per_step=3 to keep each step small
          - use_vision="auto" to only send screenshots when needed

        Args:
            needs_login: If True, creates an AgentMail inbox and injects signup
                credentials. Set False for Google-first agents that never navigate
                to login-walled sites.
        """
        from browser_use import Agent

        llm = self._build_llm()
        agent_kwargs: dict = {
            "task": task,
            "llm": llm,
            "max_failures": 2,
            "flash_mode": True,
            "enable_planning": False,
            "step_timeout": 60,
            "max_actions_per_step": 3,
            "use_vision": "auto",
        }

        # Only inject signup credentials for agents that might hit login walls
        if needs_login and (self._inbox_pool is not None or self._settings.agentmail_api_key):
            signup_email = self._get_signup_email()
            if signup_email:
                agent_kwargs["sensitive_data"] = {
                    "signup_email": signup_email,
                    "signup_password": SIGNUP_PASSWORD,
                }

        if self._settings.browser_use_api_key:
            try:
                from browser_use import Browser

                browser = Browser(use_cloud=True)
                agent_kwargs["browser"] = browser
                logger.debug(
                    "agent={} using Browser Use cloud",
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
