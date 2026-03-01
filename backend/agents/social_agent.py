"""Broader social/web presence agent for Reddit, GitHub, Medium, etc.

# RESEARCH: Checked PyGithub (7k stars), praw (3.5k stars, Reddit)
# DECISION: Browser Use for unified scraping — covers Reddit, GitHub, Medium, Substack,
#   Stack Overflow, and personal blogs in one agent pass
# ALT: Individual API wrappers (more reliable but 5+ dependencies)
"""

from __future__ import annotations

from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings


class SocialAgent(BaseBrowserAgent):
    """Scrapes broader web presence: Reddit, GitHub, Medium, Substack, Stack Overflow, blogs."""

    agent_name = "social"

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
        logger.info("social agent searching: {}", query)

        try:
            from browser_use import Agent
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=self._settings.openai_api_key,
            )

            task = (
                f"Search for '{query}' across these platforms and extract profile info:\n"
                f"1. GitHub (github.com) — username, repos, bio, contributions\n"
                f"2. Reddit (reddit.com) — username, karma, notable posts/comments\n"
                f"3. Medium (medium.com) — profile, articles written\n"
                f"4. Substack — any newsletters authored\n"
                f"5. Stack Overflow — profile, reputation, top tags\n"
                f"6. Personal blog/website — look for personal sites in search results\n\n"
                f"For each platform found, return: platform name, profile URL, "
                f"username/handle, bio, and any notable activity. "
                f"Use Google to search 'site:github.com {query}', "
                f"'site:reddit.com {query}', etc."
            )

            agent = Agent(task=task, llm=llm)
            result = await agent.run()
            final_result = result.final_result() if result else None

            if final_result:
                output_str = str(final_result)
                profiles: list[SocialProfile] = []
                urls_found: list[str] = []

                platform_indicators = {
                    "github.com": "github",
                    "reddit.com": "reddit",
                    "medium.com": "medium",
                    "substack.com": "substack",
                    "stackoverflow.com": "stackoverflow",
                    "stackexchange.com": "stackexchange",
                    "dev.to": "devto",
                    "hashnode.dev": "hashnode",
                }

                for indicator, platform in platform_indicators.items():
                    if indicator in output_str.lower():
                        url = f"https://{indicator}"
                        profiles.append(
                            SocialProfile(
                                platform=platform,
                                url=url,
                                display_name=request.person_name,
                            )
                        )
                        urls_found.append(url)

                return AgentResult(
                    agent_name=self.agent_name,
                    status=AgentStatus.SUCCESS,
                    profiles=profiles,
                    snippets=[output_str],
                    urls_found=urls_found,
                )

            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                snippets=["No broader social presence found"],
            )

        except ImportError:
            logger.warning("browser-use or langchain-openai not available for social agent")
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="browser-use or langchain-openai not installed",
            )

        except Exception as exc:
            logger.error("social agent error: {}", str(exc))
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=f"Social agent error: {exc}",
            )
