"""Autonomous account manager — creates and persists platform credentials.

# RESEARCH: No existing solution for AI agent credential management
# DECISION: Build thin layer over AgentMail + Browser Use Cloud
#   AgentMail provides disposable emails, Browser Use navigates signup flows,
#   credentials are persisted to a local JSON store for reuse across sessions.
# NOTE: On free tier AgentMail allows 3 concurrent inboxes. Create → signup → delete.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from loguru import logger

from agents.agentmail_client import AgentMailClient
from agents.cloud_skills import CloudSkillRunner
from config import Settings

# Default password for all agent-created accounts
AGENT_PASSWORD = "Jarvis2026!Ag3nt"

# Where we persist created credentials
CREDENTIALS_FILE = Path(__file__).parent.parent / "agent_credentials.json"


class AccountManager:
    """Creates, persists, and retrieves platform credentials for agents.

    Flow:
    1. Agent needs access to platform X
    2. Check credential store for existing account
    3. If none: create AgentMail inbox → run Browser Use signup task → save creds
    4. Return {email, password, username} to the agent

    Credentials are saved to a local JSON file so they survive restarts.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._mail = AgentMailClient(api_key=settings.agentmail_api_key)
        self._cloud = CloudSkillRunner(settings)
        self._lock = threading.Lock()
        self._credentials: dict[str, dict] = self._load_credentials()

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.agentmail_api_key
            and self._settings.browser_use_api_key
        )

    def _load_credentials(self) -> dict[str, dict]:
        """Load saved credentials from disk."""
        if CREDENTIALS_FILE.exists():
            try:
                data = json.loads(CREDENTIALS_FILE.read_text())
                logger.info(
                    "account_manager: loaded {} saved credentials",
                    len(data),
                )
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "account_manager: failed to load credentials: {}",
                    exc,
                )
        return {}

    def _save_credentials(self) -> None:
        """Persist credentials to disk."""
        try:
            CREDENTIALS_FILE.write_text(
                json.dumps(self._credentials, indent=2)
            )
        except OSError as exc:
            logger.error(
                "account_manager: failed to save credentials: {}", exc
            )

    def get_credentials(self, platform: str) -> dict | None:
        """Get saved credentials for a platform. Returns None if none exist."""
        with self._lock:
            creds = self._credentials.get(platform)
        if creds:
            logger.debug(
                "account_manager: found saved creds for {}",
                platform,
            )
        return creds

    def save_credentials(
        self,
        platform: str,
        email: str,
        password: str,
        username: str | None = None,
        extra: dict | None = None,
    ) -> None:
        """Save credentials for a platform."""
        with self._lock:
            self._credentials[platform] = {
                "email": email,
                "password": password,
                "username": username,
                **(extra or {}),
            }
            self._save_credentials()
        logger.info(
            "account_manager: saved creds for {} (email={})",
            platform,
            email,
        )

    async def ensure_account(
        self,
        platform: str,
        signup_url: str,
        *,
        person_name: str = "Jarvis Agent",
        timeout: float = 90.0,
    ) -> dict | None:
        """Ensure we have an account on the platform.

        Returns {email, password, username} or None if signup fails.
        """
        # Check existing
        existing = self.get_credentials(platform)
        if existing:
            return existing

        if not self.configured:
            logger.warning(
                "account_manager: not configured, can't create account "
                "for {}",
                platform,
            )
            return None

        # Create a fresh AgentMail inbox
        try:
            inbox = self._mail.create_inbox(
                label=f"signup-{platform}"
            )
            email = inbox["email"]
        except Exception as exc:
            logger.error(
                "account_manager: failed to create inbox for {}: {}",
                platform,
                exc,
            )
            return None

        # Generate a username from the email prefix
        username = email.split("@")[0].replace(".", "")[:15]

        # Run Browser Use to complete signup
        task = (
            f"Go to {signup_url} and create a new account with:\n"
            f"- Email: {email}\n"
            f"- Password: {AGENT_PASSWORD}\n"
            f"- Username/Display Name: {username}\n"
            f"- Full Name: {person_name}\n"
            f"Complete the signup form. If there's a CAPTCHA, try to "
            f"solve it. If asked for a phone number, skip or use a "
            f"placeholder. After signing up, check if there's a "
            f"verification step. Report success or failure."
        )

        try:
            result = await self._cloud.run_task(
                task,
                max_steps=15,
                timeout=timeout,
                secrets={
                    platform: f"{email}:{AGENT_PASSWORD}",
                },
            )

            if result and result.get("success"):
                self.save_credentials(
                    platform,
                    email=email,
                    password=AGENT_PASSWORD,
                    username=username,
                    extra={
                        "signup_output": result.get("output", "")[:500],
                        "inbox_id": inbox["inbox_id"],
                    },
                )

                # Check for verification email
                await self._handle_verification(
                    platform, email, inbox["inbox_id"]
                )

                return self.get_credentials(platform)

            logger.warning(
                "account_manager: signup failed for {}: {}",
                platform,
                result.get("output", "unknown")[:200] if result else "no result",
            )

        except Exception as exc:
            logger.error(
                "account_manager: signup error for {}: {}",
                platform,
                str(exc),
            )

        # Clean up the inbox on failure
        try:
            raw_client = self._mail._get_client()
            raw_client.inboxes.delete(inbox_id=email)
        except Exception:
            pass

        return None

    async def _handle_verification(
        self,
        platform: str,
        email: str,
        inbox_id: str,
    ) -> None:
        """Check for and handle verification emails."""
        import asyncio

        # Wait a few seconds for the email to arrive
        await asyncio.sleep(5)

        link = self._mail.get_verification_link(
            inbox_id, keyword="verify"
        )
        if not link:
            link = self._mail.get_verification_link(
                inbox_id, keyword="confirm"
            )

        if link:
            logger.info(
                "account_manager: found verification link for {}, "
                "clicking...",
                platform,
            )
            # Use Browser Use to click the verification link
            await self._cloud.run_task(
                f"Go to {link} and complete the verification. "
                f"Click any 'Verify' or 'Confirm' buttons.",
                max_steps=3,
                timeout=30.0,
            )

    def list_accounts(self) -> dict[str, dict]:
        """Return all saved credentials (for debugging/display)."""
        with self._lock:
            return dict(self._credentials)
