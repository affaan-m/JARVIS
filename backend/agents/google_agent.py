"""Google search research agent using browser-use.

# RESEARCH: Checked googlesearch-python (1k stars), SerpAPI (paid), Google Custom Search API
# DECISION: Browser Use for Google — avoids API key costs, can extract rich snippets
# ALT: SerpAPI if we need scale (paid, $50/mo)
"""

from __future__ import annotations

from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings


class GoogleAgent(BaseBrowserAgent):
    """Searches Google for person information via browser-use."""

    agent_name = "google"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    async def _run_task(self, request: ResearchRequest) -> AgentResult:
        if not self.configured:
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="Browser Use not configured (BROWSER_USE_API_KEY or OPENAI_API_KEY missing)",
            )

        query = self._build_search_query(request)
        logger.info("google agent searching: {}", query)

        try:
            task = (
                f"Go to google.com and search for '{query}'. "
                f"Look through the first page of results. "
                f"Extract: any social media profile links (LinkedIn, Twitter, Instagram, GitHub), "
                f"any company affiliations, job titles, notable achievements, "
                f"news articles about them, and any other relevant personal information. "
                f"List each finding with its source URL."
            )

            agent = self._create_browser_agent(task)
            result = await agent.run()
            final_result = result.final_result() if result else None

            if final_result:
                profiles: list[SocialProfile] = []
                output_str = str(final_result)

                # Extract any social profile URLs mentioned
                platform_indicators = {
                    "linkedin.com": "linkedin",
                    "twitter.com": "twitter",
                    "x.com": "twitter",
                    "instagram.com": "instagram",
                    "github.com": "github",
                    "facebook.com": "facebook",
                }

                for indicator, platform in platform_indicators.items():
                    if indicator in output_str.lower():
                        profiles.append(
                            SocialProfile(
                                platform=platform,
                                url=f"https://{indicator}",
                                display_name=request.person_name,
                            )
                        )

                return AgentResult(
                    agent_name=self.agent_name,
                    status=AgentStatus.SUCCESS,
                    profiles=profiles,
                    snippets=[output_str],
                    urls_found=[p.url for p in profiles],
                )

            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                snippets=["No Google results found"],
            )

        except ImportError:
            logger.warning("browser-use not available for google agent")
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="browser-use not installed",
            )

        except Exception as exc:
            logger.error("google agent error: {}", str(exc))
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=f"Google agent error: {exc}",
            )
