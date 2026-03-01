"""Fan-out orchestrator for research agents.

Runs LinkedIn, Twitter, Instagram, and Google agents in parallel using asyncio.gather
with return_exceptions=True so one failure doesn't kill the others.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from loguru import logger

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
from config import Settings
from observability.laminar import traced


class ResearchOrchestrator:
    """Fans out research requests to all agents in parallel and aggregates results."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._agents: list[BaseBrowserAgent] = [
            LinkedInAgent(settings),
            TwitterAgent(settings),
            InstagramAgent(settings),
            GoogleAgent(settings),
            OsintAgent(settings),
            DarkwebAgent(settings),
            SocialAgent(settings),
        ]

    @property
    def agent_names(self) -> list[str]:
        return [a.agent_name for a in self._agents]

    @traced("orchestrator.research_person")
    async def research_person(self, request: ResearchRequest) -> OrchestratorResult:
        """Run all agents in parallel and aggregate results."""
        start = time.monotonic()
        logger.info(
            "orchestrator starting research for person={} agents={}",
            request.person_name,
            self.agent_names,
        )

        # Fan out all agents in parallel with error isolation
        raw_results = await asyncio.gather(
            *[agent.run(request) for agent in self._agents],
            return_exceptions=True,
        )

        # Process results, handling any exceptions
        agent_results: dict[str, AgentResult] = {}
        all_profiles: list[SocialProfile] = []
        all_snippets: list[str] = []

        for agent, raw in zip(self._agents, raw_results, strict=True):
            if isinstance(raw, Exception):
                logger.error(
                    "orchestrator agent={} raised unhandled exception: {}",
                    agent.agent_name,
                    str(raw),
                )
                result = AgentResult(
                    agent_name=agent.agent_name,
                    status=AgentStatus.FAILED,
                    error=f"Unhandled exception: {raw}",
                    completed_at=datetime.now(UTC),
                )
            else:
                result = raw

            agent_results[agent.agent_name] = result

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

        return OrchestratorResult(
            person_name=request.person_name,
            agent_results=agent_results,
            all_profiles=_deduplicate_profiles(all_profiles),
            all_snippets=all_snippets,
            total_duration_seconds=elapsed,
            success=any_success,
            error=None if any_success else "All agents failed",
        )


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
