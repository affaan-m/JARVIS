"""OSINT research agent for public records, WHOIS, domains, and certifications.

# RESEARCH: Checked python-whois (1.8k stars), osintgram (archived), recon-ng (complex)
# DECISION: Browser Use for broad OSINT — covers WHOIS, public records, certifications in one pass
# ALT: python-whois for domain-only (too narrow)
"""

from __future__ import annotations

from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings


class OsintAgent(BaseBrowserAgent):
    """Gathers OSINT: WHOIS, public records, domains, professional certifications."""

    agent_name = "osint"

    def __init__(self, settings: Settings, *, inbox_pool=None):
        super().__init__(settings, inbox_pool=inbox_pool)

    async def _run_task(self, request: ResearchRequest) -> AgentResult:
        if not self.configured:
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="Browser Use not configured (BROWSER_USE_API_KEY or OPENAI_API_KEY missing)",
            )

        query = self._build_search_query(request)
        logger.info("osint agent searching: {}", query)

        try:
            task = (
                f"Go to https://www.google.com/search?q={query.replace(' ', '+')}+WHOIS+OR+patent+OR+trademark+OR+SEC+filing "  # noqa: E501
                f"and use the extract tool to pull OSINT findings from the FIRST page only:\n"
                f"- Domain registrations, WHOIS data\n"
                f"- Patents, trademarks, SEC filings\n"
                f"- Professional licenses, certifications\n"
                f"- Public records, court filings\n"
                f"Do NOT scroll. Do NOT click into results. "
                f"After extracting, immediately call done with the result."
            )

            agent = self._create_browser_agent(task, max_steps=3)
            result = await agent.run()
            final_result = result.final_result() if result else None

            if final_result:
                output_str = str(final_result)
                profiles: list[SocialProfile] = []
                urls_found: list[str] = []

                # Extract domain-related profiles
                domain_indicators = {
                    "who.is": "whois",
                    "whois.com": "whois",
                    "opencorporates.com": "public_records",
                    "patents.google.com": "patents",
                    "uspto.gov": "patents",
                    "sec.gov": "public_records",
                }

                for indicator, platform in domain_indicators.items():
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
                snippets=["No OSINT records found"],
            )

        except ImportError:
            logger.warning("browser-use not available for osint agent")
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="browser-use not installed",
            )

        except Exception as exc:
            logger.error("osint agent error: {}", str(exc))
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=f"OSINT agent error: {exc}",
            )
