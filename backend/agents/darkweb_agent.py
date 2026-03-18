"""Dark web / breach database research agent.

# RESEARCH: Checked haveibeenpwned API (official, needs API key), dehashed (paid API)
# DECISION: HIBP API for breach metadata — official, well-documented, returns breach names/dates
# ALT: DeHashed for deeper leak metadata (paid, needs separate key)
# NOTE: We only collect breach metadata (service names, dates, counts). Never passwords.
"""

from __future__ import annotations

import httpx
from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings

HIBP_BASE_URL = "https://haveibeenpwned.com/api/v3"
HIBP_TIMEOUT_SECONDS = 30.0


class DarkwebAgent(BaseBrowserAgent):
    """Checks breach/leak databases for email exposure metadata.

    Uses Have I Been Pwned API. Returns breach count, affected services, and dates.
    Never collects or stores passwords.
    """

    agent_name = "darkweb"

    def __init__(self, settings: Settings, *, inbox_pool=None):
        super().__init__(settings, inbox_pool=inbox_pool)

    @property
    def configured(self) -> bool:
        return bool(self._settings.hibp_api_key)

    async def _run_task(self, request: ResearchRequest) -> AgentResult:
        if not self.configured:
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="HIBP_API_KEY not configured",
            )

        # Build potential email addresses to check
        emails = self._guess_emails(request)
        if not emails:
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                snippets=["No email addresses to check against breach databases"],
            )

        all_snippets: list[str] = []
        all_profiles: list[SocialProfile] = []
        total_breaches = 0

        async with httpx.AsyncClient(timeout=HIBP_TIMEOUT_SECONDS) as client:
            for email in emails:
                breaches = await self._check_hibp(client, email)
                if breaches is None:
                    continue

                if not breaches:
                    all_snippets.append(f"{email}: No breaches found")
                    continue

                total_breaches += len(breaches)
                breach_names = [b.get("Name", "Unknown") for b in breaches]
                breach_dates = [b.get("BreachDate", "Unknown") for b in breaches]
                domains = [b.get("Domain", "") for b in breaches]

                all_snippets.append(
                    f"{email}: {len(breaches)} breaches — "
                    f"services: {', '.join(breach_names[:10])}"
                )

                all_profiles.append(
                    SocialProfile(
                        platform="hibp",
                        url=f"https://haveibeenpwned.com/account/{email}",
                        username=email,
                        display_name=request.person_name,
                        bio=f"{len(breaches)} breaches found",
                        raw_data={
                            "breach_count": len(breaches),
                            "breach_names": breach_names,
                            "breach_dates": breach_dates,
                            "domains": [d for d in domains if d],
                        },
                    )
                )

        if not all_snippets:
            all_snippets.append("Breach database check completed — no results")

        return AgentResult(
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            profiles=all_profiles,
            snippets=all_snippets,
            urls_found=[p.url for p in all_profiles],
        )

    async def _check_hibp(
        self, client: httpx.AsyncClient, email: str
    ) -> list[dict] | None:
        """Query HIBP for breaches associated with an email. Returns None on error."""
        try:
            logger.info("darkweb agent checking HIBP for: {}", email)
            resp = await client.get(
                f"{HIBP_BASE_URL}/breachedaccount/{email}",
                headers={
                    "hibp-api-key": self._settings.hibp_api_key,
                    "user-agent": "JARVIS-Research-Agent",
                },
                params={"truncateResponse": "false"},
            )

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                return []
            if resp.status_code == 429:
                logger.warning("HIBP rate limited for {}", email)
                return None

            logger.warning("HIBP returned {} for {}", resp.status_code, email)
            return None

        except Exception as exc:
            logger.error("HIBP request failed for {}: {}", email, str(exc))
            return None

    def _guess_emails(self, request: ResearchRequest) -> list[str]:
        """Generate likely email addresses from person name and company."""
        parts = request.person_name.lower().split()
        if len(parts) < 2:
            return []

        first, last = parts[0], parts[-1]
        emails: list[str] = []

        if request.company:
            domain = request.company.lower().replace(" ", "").replace(",", "")
            emails.extend([
                f"{first}.{last}@{domain}.com",
                f"{first[0]}{last}@{domain}.com",
                f"{first}@{domain}.com",
            ])

        # Common free email patterns
        emails.extend([
            f"{first}.{last}@gmail.com",
            f"{first}{last}@gmail.com",
        ])

        return emails
