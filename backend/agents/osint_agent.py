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
        logger.info("osint agent searching: {}", query)

        try:
            task = (
                f"Research '{query}' across public OSINT sources. "
                f"1. Check WHOIS records for domains registered to this person or company. "
                f"2. Look for professional certifications or licenses "
                f"(e.g. state bar, medical license, CPA, real estate). "
                f"3. Search public records databases for business filings, patents, trademarks. "
                f"4. Check domain registration history on who.is or similar. "
                f"Return all findings with source URLs in a structured format."
            )

            agent = self._create_browser_agent(task)
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
