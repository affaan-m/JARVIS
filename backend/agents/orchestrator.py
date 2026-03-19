"""Two-phase research orchestrator.

Phase 1: Static agents (LinkedIn, Twitter, Instagram, Google, OSINT, Social) + Exa in parallel.
Phase 2: Dynamic URL scrapers for high-value URLs discovered by Exa/Google that aren't
         already covered by a static agent.

All phases run concurrently. Results stream back as agents complete.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from loguru import logger

from agents.agentmail_client import AgentMailClient, InboxPool
from agents.browser_agent import BaseBrowserAgent
from agents.darkweb_agent import DarkwebAgent
from agents.google_agent import GoogleAgent
from agents.instagram_agent import InstagramAgent
from agents.linkedin_agent import LinkedInAgent
from agents.models import (
    AgentResult,
    AgentStatus,
    OrchestratorResult,
    ResearchRequest,
    SocialProfile,
)
from agents.osint_agent import OsintAgent
from agents.social_agent import SocialAgent
from agents.twitter_agent import TwitterAgent
from agents.url_scraper_agent import UrlScraperAgent
from config import Settings
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest
from observability.laminar import traced

# Domains already covered by dedicated agents — don't spawn scrapers for these
COVERED_DOMAINS = frozenset({
    "linkedin.com", "www.linkedin.com",
    "twitter.com", "x.com", "www.x.com",
    "instagram.com", "www.instagram.com",
    "google.com", "www.google.com",
    "youtube.com", "www.youtube.com",
    "facebook.com", "www.facebook.com",
})

# Max dynamic scrapers to spawn (avoid burning too many cloud browsers)
MAX_DYNAMIC_SCRAPERS = 3


class ResearchOrchestrator:
    """Two-phase orchestrator: static agents + dynamic URL scrapers.

    Creates a shared InboxPool so all agents get pre-warmed email
    addresses for login-wall bypass without on-demand API latency.
    """

    def __init__(self, settings: Settings, *, pool_size: int = 10):
        self._settings = settings
        self._exa = ExaEnrichmentClient(settings)

        # Create shared inbox pool if AgentMail is configured
        self._inbox_pool: InboxPool | None = None
        if settings.agentmail_api_key:
            mail_client = AgentMailClient(api_key=settings.agentmail_api_key)
            self._inbox_pool = InboxPool(mail_client, pool_size=pool_size)
            logger.info("orchestrator: inbox pool created, pool_size={}", pool_size)

        self._static_agents: list[BaseBrowserAgent] = [
            LinkedInAgent(settings, inbox_pool=self._inbox_pool),
            TwitterAgent(settings, inbox_pool=self._inbox_pool),
            InstagramAgent(settings, inbox_pool=self._inbox_pool),
            GoogleAgent(settings, inbox_pool=self._inbox_pool),
            OsintAgent(settings, inbox_pool=self._inbox_pool),
            SocialAgent(settings, inbox_pool=self._inbox_pool),
        ]
        darkweb = DarkwebAgent(settings, inbox_pool=self._inbox_pool)
        if darkweb.configured:
            self._static_agents.append(darkweb)

    @property
    def agent_names(self) -> list[str]:
        return [a.agent_name for a in self._static_agents]

    @traced("orchestrator.research_person")
    async def research_person(self, request: ResearchRequest) -> OrchestratorResult:
        """Run Exa + static agents in parallel, then spawn dynamic scrapers for discovered URLs."""
        start = time.monotonic()
        timeout = request.timeout_seconds or 90.0

        logger.info(
            "orchestrator starting research for person={} agents={} timeout={}s",
            request.person_name,
            self.agent_names,
            timeout,
        )

        # Phase 1: Launch Exa + all static agents in parallel
        exa_req = EnrichmentRequest(name=request.person_name, company=request.company)
        exa_task = asyncio.create_task(self._exa.enrich_person(exa_req), name="exa")

        tasks: dict[str, asyncio.Task] = {"exa": exa_task}
        for agent in self._static_agents:
            task = asyncio.create_task(agent.run(request), name=agent.agent_name)
            tasks[agent.agent_name] = task

        # Wait for all with the overall timeout
        done, pending = await asyncio.wait(
            tasks.values(),
            timeout=timeout,
        )

        # Cancel any stragglers
        for task in pending:
            task.cancel()

        # Collect results from static agents
        agent_results: dict[str, AgentResult] = {}
        all_profiles: list[SocialProfile] = []
        all_snippets: list[str] = []

        # Handle Exa result
        exa_result = None
        if exa_task in done and not exa_task.exception():
            exa_result = exa_task.result()
            if exa_result.success:
                for hit in exa_result.hits:
                    all_snippets.append(f"[Exa] {hit.title}: {hit.snippet[:200]}" if hit.snippet else f"[Exa] {hit.title}")  # noqa: E501
                agent_results["exa"] = AgentResult(
                    agent_name="exa",
                    status=AgentStatus.SUCCESS,
                    snippets=[h.snippet or h.title for h in exa_result.hits],
                    urls_found=[h.url for h in exa_result.hits],
                    duration_seconds=time.monotonic() - start,
                    completed_at=datetime.now(UTC),
                )

        # Handle static agent results
        for agent_name, task in tasks.items():
            if agent_name == "exa":
                continue
            if task in pending:
                elapsed_agent = time.monotonic() - start
                logger.warning(
                    "orchestrator agent={} cancelled (overall timeout) elapsed={:.1f}s",
                    agent_name, elapsed_agent,
                )
                result = AgentResult(
                    agent_name=agent_name,
                    status=AgentStatus.TIMEOUT,
                    error="Cancelled by orchestrator timeout",
                    duration_seconds=elapsed_agent,
                    completed_at=datetime.now(UTC),
                )
            elif task.exception():
                exc = task.exception()
                logger.error(
                    "orchestrator agent={} raised: {}",
                    agent_name, str(exc),
                )
                result = AgentResult(
                    agent_name=agent_name,
                    status=AgentStatus.FAILED,
                    error=f"Unhandled exception: {exc}",
                    completed_at=datetime.now(UTC),
                )
            else:
                result = task.result()

            agent_results[agent_name] = result

            if result.status == AgentStatus.SUCCESS:
                all_profiles.extend(result.profiles)
                all_snippets.extend(result.snippets)

        # Phase 2: Dynamic scrapers for high-value URLs from Exa
        remaining_time = timeout - (time.monotonic() - start)
        if exa_result and exa_result.success and remaining_time > 15:
            dynamic_results = await self._run_dynamic_scrapers(
                request, exa_result.hits, remaining_time,
            )
            for name, result in dynamic_results.items():
                agent_results[name] = result
                if result.status == AgentStatus.SUCCESS:
                    all_profiles.extend(result.profiles)
                    all_snippets.extend(result.snippets)

        elapsed = time.monotonic() - start
        any_success = any(r.status == AgentStatus.SUCCESS for r in agent_results.values())

        logger.info(
            "orchestrator completed person={} elapsed={:.1f}s agents_success={}/{} "
            "total_profiles={} total_snippets={}",
            request.person_name,
            elapsed,
            sum(1 for r in agent_results.values() if r.status == AgentStatus.SUCCESS),
            len(agent_results),
            len(all_profiles),
            len(all_snippets),
        )

        # Clean up inbox pool (delete temporary inboxes to free concurrent slots)
        if self._inbox_pool:
            self._inbox_pool.release_all()

        return OrchestratorResult(
            person_name=request.person_name,
            agent_results=agent_results,
            all_profiles=_deduplicate_profiles(all_profiles),
            all_snippets=all_snippets,
            total_duration_seconds=elapsed,
            success=any_success,
            error=None if any_success else "All agents failed",
        )

    async def _run_dynamic_scrapers(
        self,
        request: ResearchRequest,
        hits: list,
        timeout: float,
    ) -> dict[str, AgentResult]:
        """Spawn URL scrapers for high-value URLs not covered by static agents."""
        urls_to_scrape: list[str] = []

        for hit in hits:
            if not hit.url:
                continue
            domain = urlparse(hit.url).netloc.lower()
            if domain in COVERED_DOMAINS:
                continue
            # Skip generic pages (Wikipedia, news sites have low per-person value)
            if any(skip in domain for skip in ("wikipedia.org", "wikidata.org")):
                continue
            urls_to_scrape.append(hit.url)

        if not urls_to_scrape:
            return {}

        urls_to_scrape = urls_to_scrape[:MAX_DYNAMIC_SCRAPERS]
        logger.info(
            "orchestrator spawning {} dynamic scrapers: {}",
            len(urls_to_scrape),
            urls_to_scrape,
        )

        scraper_tasks: dict[str, asyncio.Task] = {}
        for url in urls_to_scrape:
            scraper = UrlScraperAgent(
                self._settings, url=url, source="exa", inbox_pool=self._inbox_pool,
            )
            task = asyncio.create_task(
                scraper.run(request),
                name=scraper.agent_name,
            )
            scraper_tasks[scraper.agent_name] = task

        done, pending = await asyncio.wait(
            scraper_tasks.values(),
            timeout=timeout,
        )

        for task in pending:
            task.cancel()

        results: dict[str, AgentResult] = {}
        for name, task in scraper_tasks.items():
            if task in pending:
                results[name] = AgentResult(
                    agent_name=name,
                    status=AgentStatus.TIMEOUT,
                    error="Dynamic scraper timed out",
                    completed_at=datetime.now(UTC),
                )
            elif task.exception():
                results[name] = AgentResult(
                    agent_name=name,
                    status=AgentStatus.FAILED,
                    error=str(task.exception()),
                    completed_at=datetime.now(UTC),
                )
            else:
                results[name] = task.result()

        return results


def _deduplicate_profiles(profiles: list[SocialProfile]) -> list[SocialProfile]:
    """Remove duplicate profiles by (platform, url) pair."""
    seen: set[tuple[str, str]] = set()
    unique: list[SocialProfile] = []
    for profile in profiles:
        key = (profile.platform, profile.url)
        if key not in seen:
            seen.add(key)
            unique.append(profile)
    return unique
