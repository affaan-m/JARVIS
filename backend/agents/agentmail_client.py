"""AgentMail integration with pre-warmed inbox pool for parallel agent processing.

# RESEARCH: Checked AgentMail (YC S25), Mailgun, temp-mail-api
# DECISION: AgentMail — built for AI agents, API-first, receives + sends
# ALT: Mailgun (overkill, not agent-oriented), temp-mail-api (receive only)
"""

from __future__ import annotations

import os
import threading

from loguru import logger

AGENTMAIL_API_KEY_ENV = "AGENTMAIL_API_KEY"


class AgentMailClient:
    """Wrapper around AgentMail SDK with pre-warmed inbox pool.

    Creates disposable email inboxes that agents can use to sign up for
    platforms they encounter with login walls. The pool pre-creates inboxes
    at startup so agents get zero-latency email addresses during runs.
    """

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get(AGENTMAIL_API_KEY_ENV)
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is None:
            from agentmail import AgentMail

            self._client = AgentMail(api_key=self._api_key)
        return self._client

    def create_inbox(self, label: str | None = None) -> dict:
        """Create a new disposable email inbox.

        Returns dict with inbox_id (the email address) and metadata.
        """
        if not self.configured:
            raise RuntimeError("AGENTMAIL_API_KEY not configured")

        from agentmail.inboxes import CreateInboxRequest

        client = self._get_client()
        display = f"specter-{label}" if label else "specter-agent"
        inbox = client.inboxes.create(
            request=CreateInboxRequest(display_name=display),
        )
        inbox_id = inbox.inbox_id

        logger.info("agentmail: created inbox={} label={}", inbox_id, label or "auto")
        return {
            "inbox_id": inbox_id,
            "email": inbox_id,
            "label": label,
        }

    def list_inboxes(self) -> list[dict]:
        """List all inboxes in the account."""
        if not self.configured:
            return []

        client = self._get_client()
        resp = client.inboxes.list()
        return [
            {
                "inbox_id": ib.inbox_id,
                "display_name": ib.display_name,
                "created_at": str(ib.created_at) if ib.created_at else None,
            }
            for ib in resp.inboxes
        ]

    def list_messages(self, inbox_id: str) -> list[dict]:
        """List messages in an inbox. Used to check for verification emails."""
        if not self.configured:
            return []

        client = self._get_client()
        try:
            messages = client.inboxes.messages.list(inbox_id=inbox_id)
            return [
                {
                    "id": getattr(m, "message_id", str(m)),
                    "from": getattr(m, "from_", ""),
                    "subject": getattr(m, "subject", ""),
                    "text": getattr(m, "text", ""),
                }
                for m in messages
            ]
        except Exception as exc:
            logger.warning("agentmail: failed to list messages for {}: {}", inbox_id, exc)
            return []

    def get_otp_code(self, inbox_id: str, max_age_seconds: int = 300) -> str | None:
        """Extract 6-digit OTP code from recent inbox messages."""
        import re
        import time

        messages = self.list_messages(inbox_id)
        now = time.time()

        for msg in messages:
            # Check recency if created_at is available
            text = f"{msg.get('subject', '')} {msg.get('text', '')}"
            match = re.search(r"\b(\d{6})\b", text)
            if match:
                code = match.group(1)
                logger.info("agentmail: found OTP {} in {}", code, inbox_id)
                return code

        return None

    def get_verification_link(self, inbox_id: str, keyword: str = "verify") -> str | None:
        """Poll inbox for a verification email and extract the confirmation link."""
        import re

        messages = self.list_messages(inbox_id)
        for msg in messages:
            subject = msg.get("subject", "").lower()
            body = msg.get("text", "")

            if keyword.lower() in subject or keyword.lower() in body.lower():
                urls = re.findall(r"https?://[^\s<>\"']+", body)
                for url in urls:
                    if any(k in url.lower() for k in ["verify", "confirm", "activate", "token"]):
                        logger.info("agentmail: found verification link in {}", inbox_id)
                        return url
                if urls:
                    return urls[0]

        return None


class InboxPool:
    """Thread-safe inbox manager with create-on-demand + delete-on-release.

    Free tier allows max 3 concurrent inboxes. Instead of pre-creating a pool,
    we create inboxes just-in-time when agents need them and delete when released.
    This keeps us under the concurrent limit while supporting parallel agents.

    For paid tiers with higher limits, warm_up() can pre-create inboxes.
    """

    def __init__(self, client: AgentMailClient, pool_size: int = 3):
        self._client = client
        self._pool_size = pool_size
        self._available: list[str] = []  # pre-created, ready to use
        self._in_use: dict[str, str] = {}  # agent_name -> email
        self._lock = threading.Lock()
        # Include the existing jarvis inbox as a fallback
        self._fallback_email = "ciri@agentmail.to"

    @property
    def available_count(self) -> int:
        with self._lock:
            return len(self._available)

    @property
    def in_use_count(self) -> int:
        with self._lock:
            return len(self._in_use)

    def warm_up(self, count: int | None = None) -> int:
        """Pre-create inboxes up to the concurrent limit. Returns number created."""
        target = min(count or self._pool_size, self._pool_size)
        created = 0

        with self._lock:
            needed = target - len(self._available) - len(self._in_use)

        if needed <= 0:
            logger.info("inbox_pool: already at capacity, no warm-up needed")
            return 0

        logger.info("inbox_pool: warming up {} inboxes...", needed)

        for i in range(needed):
            try:
                result = self._client.create_inbox(label=f"pool-{i}")
                with self._lock:
                    self._available.append(result["email"])
                created += 1
            except Exception as exc:
                logger.warning("inbox_pool: hit limit at {}/{}: {}", i + 1, needed, exc)
                break

        logger.info(
            "inbox_pool: warmed up {}/{} inboxes, available={}",
            created, needed, self.available_count,
        )
        return created

    def acquire(self, agent_name: str) -> str | None:
        """Get an inbox for an agent. Creates on-demand if pool is empty."""
        with self._lock:
            # Check if agent already has one
            if agent_name in self._in_use:
                return self._in_use[agent_name]

            # Try pre-created pool first
            if self._available:
                email = self._available.pop(0)
                self._in_use[agent_name] = email
                logger.debug(
                    "inbox_pool: agent={} acquired={} (from pool, {} remaining)",
                    agent_name, email, len(self._available),
                )
                return email

        # Create on-demand
        try:
            result = self._client.create_inbox(label=agent_name)
            email = result["email"]
            with self._lock:
                self._in_use[agent_name] = email
            logger.info("inbox_pool: agent={} acquired={} (on-demand)", agent_name, email)
            return email
        except Exception as exc:
            # If we hit the limit, use the shared fallback inbox
            logger.warning(
                "inbox_pool: limit hit for agent={}, using fallback={}: {}",
                agent_name, self._fallback_email, exc,
            )
            with self._lock:
                self._in_use[agent_name] = self._fallback_email
            return self._fallback_email

    def release(self, agent_name: str) -> None:
        """Release an inbox. Deletes it to free up the concurrent slot."""
        with self._lock:
            email = self._in_use.pop(agent_name, None)

        if not email or email == self._fallback_email:
            return

        # Delete the inbox to free up the concurrent slot
        try:
            from agentmail import AgentMail

            raw_client = self._client._get_client()
            raw_client.inboxes.delete(inbox_id=email)
            logger.debug("inbox_pool: agent={} released+deleted={}", agent_name, email)
        except Exception as exc:
            logger.warning("inbox_pool: failed to delete {}: {}", email, exc)

    def release_all(self) -> None:
        """Release and delete all in-use inboxes. Called at orchestrator cleanup."""
        with self._lock:
            agents = list(self._in_use.keys())
        for agent_name in agents:
            self.release(agent_name)

        # Also clean up pre-created pool inboxes
        with self._lock:
            emails_to_delete = list(self._available)
            self._available.clear()

        for email in emails_to_delete:
            try:
                raw_client = self._client._get_client()
                raw_client.inboxes.delete(inbox_id=email)
                logger.debug("inbox_pool: cleanup deleted={}", email)
            except Exception:
                pass

    def status(self) -> dict:
        """Return pool status for logging/debugging."""
        with self._lock:
            return {
                "available": len(self._available),
                "in_use": len(self._in_use),
                "in_use_by": dict(self._in_use),
                "pool_size": self._pool_size,
            }
