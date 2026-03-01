"""Browser Use Cloud SDK skill runner + autonomous task executor.

# RESEARCH: browser-use-sdk v2.0.15 — official Cloud API client
# DECISION: Use create_task with skill_ids for marketplace skills ($0.01/run, ~23s)
#   Also use create_task WITHOUT skills for arbitrary URL extraction/scraping
# NOTE: Tested live — TikTok skill returned real profile data in 23s for $0.012
"""

from __future__ import annotations

import asyncio

from loguru import logger

from config import Settings

# ─── Cloned skill registry (26 skills in account) ───────────────────────────
# All IDs verified via client.skills.list_skills() — Feb 28, 2026
SKILL_IDS = {
    # Social Media — person research
    "tiktok_profile": "60e6940b-eb2c-4d54-aa54-0012ff6b6a8d",
    "tiktok_videos": "727f4185-3ee9-41ef-833b-456f63140bc8",
    "tiktok_search": "c7941bac-f0e2-4e23-8e8e-ecf2494047cd",
    "instagram_posts": "dc6b4dac-f983-488b-9f15-81cdef09a2a5",
    "facebook_page": "07bca652-0668-4836-9a89-68f728a6b922",
    "linktree_profile": "4d3cc402-f840-4939-9f2b-0f707adf67d1",
    "pinterest_pins": "7dffd877-5c0f-4c72-a1c2-6f7d641a3283",
    "youtube_filmography": "f5d4c977-126e-4374-b1b3-8b02942dfa1c",
    "reddit_subreddit": "4693909a-7d0e-4628-8e0d-1cab01271a3c",
    # Professional / OSINT
    "linkedin_company_posts": "b50a1f27-22a6-489f-9768-83c0c52e8207",
    "company_employees": "47634a96-110e-4da0-ace5-8c520af7d9c3",
    "github_profile": "bcc9987f-7bc7-4af5-8c8e-7046be487e64",
    "sec_filings": "ce6cc606-837a-44d0-94e7-977d8b470113",
    "whois_lookup": "a9bf3a53-d58f-4a09-9a29-d5663a33937b",
    "osint_scraper": "2a607934-bf3e-43d9-aaa2-30f2b419eaf5",
    "yc_company": "cc661bb6-e3f3-4a48-9012-08b252a0a0bb",
    "ancestry_records": "b985c331-4515-4702-bc64-be75f429aee3",
    # Utility
    "website_scraper": "6b4792a2-5665-46e2-93ba-df0d45ca9171",
    "autonomous_workflow": "f467e930-457c-4edc-a8fc-c307038fc566",
    "geocoder": "8349909a-4113-4a93-9061-aed21dc7ea32",
    # Records
    "prisoner_records": "b4148789-8b38-4799-8d4e-f5439f55dc84",
}

# Marketplace-only IDs (work via create_task with skill_ids, no cloning needed)
MARKETPLACE_SKILL_IDS = {
    "tiktok_profile_mp": "88542a65-c3f7-4c37-90c9-e8c5aa974094",
    "instagram_posts_mp": "59829921-8cd7-4636-b190-ee67124d9eb2",
    "linkedin_posts_mp": "5f5dbbfa-1749-4a42-9c20-3341f71953cb",
    "linkedin_connections_mp": "01ca8c45-81ae-4946-84e4-72a759cdf369",
    "facebook_page_mp": "a3242bc1-f92d-4aac-91a9-43a61482cb95",
    "social_follower_verify": "dc2ee351-eb79-436b-ae76-052665078699",
    "linktree_profile_mp": "54d01398-b271-4d36-ae1f-ff20bd106596",
}

# Poll settings
POLL_INTERVAL_SECONDS = 2.0


class CloudSkillRunner:
    """Runs Browser Use Cloud tasks — with or without marketplace skills.

    Two modes:
    1. run_skill(skill_name, task) — guided by a marketplace/cloned skill
    2. run_task(task) — freeform browser task (for deep URL extraction)

    If a profile_id is configured (via BROWSER_USE_PROFILE_ID), all tasks
    run in a session that inherits synced browser cookies (login states).
    This is the Browser Use Cloud approach to auth — sync cookies once,
    use everywhere.
    """

    def __init__(self, settings: Settings):
        self._api_key = settings.browser_use_api_key
        self._profile_id = settings.browser_use_profile_id
        self._op_vault_id = settings.op_vault_id
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from browser_use_sdk import AsyncBrowserUse

            self._client = AsyncBrowserUse(api_key=self._api_key)
            return self._client
        except ImportError:
            logger.warning("browser_use_sdk not installed")
            return None

    async def _create_fresh_session(self) -> str | None:
        """Create a fresh authenticated session from synced browser profile.

        Each task gets its own session — Browser Use sessions are single-use
        and stop after a task completes. The profile stores cookies from all
        platforms the agent is logged into.
        """
        if not self._profile_id:
            return None

        client = self._get_client()
        if not client:
            return None

        try:
            session = await client.sessions.create_session(
                profile_id=self._profile_id,
                proxy_country_code="us",
                persist_memory=True,
            )
            logger.debug(
                "cloud_skills: fresh session {} from profile {}",
                session.id, self._profile_id[:16],
            )
            return session.id
        except Exception as exc:
            logger.warning("cloud_skills: session creation failed: {}", exc)
            return None

    async def run_skill(
        self,
        skill_name: str,
        task: str,
        *,
        max_steps: int = 5,
        timeout: float = 60.0,
        secrets: dict[str, str] | None = None,
        allowed_domains: list[str] | None = None,
    ) -> dict | None:
        """Run a skill-guided task and wait for completion."""
        if not self.configured:
            return None

        # Check both registries
        skill_id = SKILL_IDS.get(skill_name) or MARKETPLACE_SKILL_IDS.get(
            skill_name
        )
        if not skill_id:
            logger.error("cloud_skills: unknown skill '{}'", skill_name)
            return None

        return await self._create_and_poll(
            task,
            skill_ids=[skill_id],
            max_steps=max_steps,
            timeout=timeout,
            secrets=secrets,
            allowed_domains=allowed_domains,
            label=skill_name,
        )

    async def run_task(
        self,
        task: str,
        *,
        max_steps: int = 10,
        timeout: float = 90.0,
        secrets: dict[str, str] | None = None,
        allowed_domains: list[str] | None = None,
    ) -> dict | None:
        """Run a freeform browser task (no skill). For deep URL extraction."""
        if not self.configured:
            return None
        return await self._create_and_poll(
            task,
            max_steps=max_steps,
            timeout=timeout,
            secrets=secrets,
            allowed_domains=allowed_domains,
            label="freeform",
        )

    async def _create_and_poll(
        self,
        task: str,
        *,
        skill_ids: list[str] | None = None,
        max_steps: int = 10,
        timeout: float = 60.0,
        secrets: dict[str, str] | None = None,
        allowed_domains: list[str] | None = None,
        label: str = "task",
    ) -> dict | None:
        """Core create_task + polling loop."""
        client = self._get_client()
        if client is None:
            return None

        try:
            create_kwargs: dict = {
                "task": task,
                "llm": "browser-use-2.0",
                "max_steps": max_steps,
            }
            if skill_ids:
                create_kwargs["skill_ids"] = skill_ids
            if secrets:
                create_kwargs["secrets"] = secrets
            if allowed_domains:
                create_kwargs["allowed_domains"] = allowed_domains
            # 1Password vault for cross-session auth (logins, OTP)
            if self._op_vault_id:
                create_kwargs["op_vault_id"] = self._op_vault_id

            logger.info(
                "cloud_skills: creating task label={} preview={} vault={}",
                label,
                task[:80],
                bool(self._op_vault_id),
            )

            result = await client.tasks.create_task(**create_kwargs)
            task_id = result.id
            # Grab live URL for real-time viewing
            live_url = getattr(result, "live_url", None) or getattr(result, "liveUrl", None)
            max_polls = int(timeout / POLL_INTERVAL_SECONDS)

            for _ in range(max_polls):
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                status = await client.tasks.get_task_status(task_id)

                if status.status in ("finished", "stopped"):
                    output = {
                        "output": status.output or "",
                        "success": bool(status.is_success),
                        "cost": str(status.cost) if status.cost else "unknown",
                        "task_id": task_id,
                        "live_url": live_url,
                        "label": label,
                    }
                    logger.info(
                        "cloud_skills: completed label={} success={} cost={}",
                        label,
                        output["success"],
                        output["cost"],
                    )
                    return output

            logger.warning(
                "cloud_skills: timed out label={} after {:.0f}s",
                label,
                timeout,
            )
            return {"output": "", "success": False, "task_id": task_id, "live_url": live_url, "label": label, "timed_out": True}

        except Exception as exc:
            logger.error(
                "cloud_skills: error label={}: {}", label, str(exc)
            )
            return None

    async def run_parallel(
        self,
        tasks: list[dict],
        *,
        timeout: float = 60.0,
    ) -> list[dict | None]:
        """Run multiple skill tasks in parallel.

        Each dict should have: skill_name, task, and optional kwargs.
        """
        coros = []
        for t in tasks:
            t = dict(t)  # don't mutate caller's data
            skill_name = t.pop("skill_name", None)
            task_str = t.pop("task")
            if skill_name:
                coros.append(
                    self.run_skill(
                        skill_name, task_str, timeout=timeout, **t
                    )
                )
            else:
                coros.append(
                    self.run_task(task_str, timeout=timeout, **t)
                )

        return list(await asyncio.gather(*coros, return_exceptions=False))

    async def deep_extract_url(
        self,
        url: str,
        person_name: str,
        *,
        timeout: float = 60.0,
        secrets: dict[str, str] | None = None,
    ) -> dict | None:
        """Navigate to a URL and extract maximal person information.

        Uses the website_scraper skill for general URLs, or freeform
        task for deeper extraction. Returns structured output.
        """
        task = (
            f"Navigate to {url} and extract ALL information about "
            f"'{person_name}'. Get: full name, title, bio, company, "
            f"social links, achievements, education, publications, "
            f"contact info, photos, and any other relevant data. "
            f"Be thorough — extract everything visible on the page."
        )
        return await self.run_task(
            task, max_steps=8, timeout=timeout, secrets=secrets,
        )
