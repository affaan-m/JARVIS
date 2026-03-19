"""Dynamic URL scraper agent — navigates to any URL and extracts person-related info.

# RESEARCH: This is the core of the dynamic agent architecture.
# Instead of one agent per platform, the orchestrator spawns these for each
# discovered URL (from Exa, Google agent, or any other source).
# DECISION: Browser Use with extract tool — fastest way to pull structured data from any page.
"""

from __future__ import annotations

from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings


class UrlScraperAgent(BaseBrowserAgent):
    """Scrapes a specific URL for person-related information.

    Unlike platform-specific agents, this takes a URL and extracts whatever
    person data it can find. Used by the orchestrator to deep-dive URLs
    discovered during the initial sweep.
    """

    agent_name = "url_scraper"

    def __init__(self, settings: Settings, *, url: str, source: str = "discovered", inbox_pool=None):  # noqa: E501
        super().__init__(settings, inbox_pool=inbox_pool)
        self._target_url = url
        self._source = source
        # Use URL domain as agent name for tracing
        from urllib.parse import urlparse

        domain = urlparse(url).netloc.replace("www.", "")
        self.agent_name = f"scrape:{domain}"

    async def _run_task(self, request: ResearchRequest) -> AgentResult:
        if not self.configured:
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="Browser Use not configured",
            )

        logger.info("url_scraper navigating to: {}", self._target_url)

        try:
            task = (
                f"Go to {self._target_url} and use the extract tool to get all information "
                f"about '{request.person_name}' from this page. Extract:\n"
                f"- Name, title, role, bio\n"
                f"- Company affiliations\n"
                f"- Contact info, social links\n"
                f"- Key facts, achievements, quotes\n"
                f"Return a comprehensive summary. Do NOT navigate away from this page."
            )

            agent = self._create_browser_agent(task, max_steps=3)
            result = await agent.run()
            final_result = result.final_result() if result else None

            if final_result:
                output_str = str(final_result)
                profile = SocialProfile(
                    platform=self._source,
                    url=self._target_url,
                    display_name=request.person_name,
                    raw_data={"extracted_text": output_str},
                )

                return AgentResult(
                    agent_name=self.agent_name,
                    status=AgentStatus.SUCCESS,
                    profiles=[profile],
                    snippets=[output_str[:500]],
                    urls_found=[self._target_url],
                )

            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                snippets=[f"No data extracted from {self._target_url}"],
            )

        except ImportError:
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="browser-use not installed",
            )

        except Exception as exc:
            logger.error("url_scraper error for {}: {}", self._target_url, str(exc))
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=f"URL scraper error: {exc}",
            )
