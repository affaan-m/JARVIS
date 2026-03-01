"""LinkedIn research agent using browser-use with authenticated session support.

# RESEARCH: Checked linkedin-api (2k stars, unofficial), linkedin-scraper (archived)
# DECISION: Browser Use + Voyager API interception — most reliable for public profiles
# ALT: linkedin-api (gets rate-limited fast, account bans)
"""

from __future__ import annotations

import json

from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings


class LinkedInAgent(BaseBrowserAgent):
    """Scrapes LinkedIn profiles via browser-use with authenticated session.

    Extracts: headline, experience, education, skills, connections count, recent posts.
    Authenticated session bypasses the login wall for richer data.
    """

    agent_name = "linkedin"

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
        logger.info("linkedin agent searching: {}", query)

        try:
            task = (
                f"Go to linkedin.com and search for '{query}'. "
                f"Find the most likely profile for this person. "
                f"Click into their profile page and extract ALL of the following in JSON format:\n"
                f'{{"full_name": "...", "headline": "...", "location": "...", '
                f'"about": "...", "current_company": "...", "current_title": "...", '
                f'"experience": [{{"title": "...", "company": "...", "duration": "..."}}], '
                f'"education": [{{"school": "...", "degree": "...", "field": "..."}}], '
                f'"skills": ["..."], "connections_count": "...", '
                f'"recent_posts": [{{"text": "...", "date": "..."}}], '
                f'"profile_url": "..."}}\n'
                f"Return ONLY the JSON object, no other text."
            )

            agent = self._create_browser_agent(task)
            result = await agent.run()
            final_result = result.final_result() if result else None

            if final_result:
                parsed = _parse_linkedin_output(str(final_result), request.person_name)
                return AgentResult(
                    agent_name=self.agent_name,
                    status=AgentStatus.SUCCESS,
                    profiles=[parsed["profile"]],
                    snippets=parsed["snippets"],
                    urls_found=[parsed["profile"].url] if parsed["profile"].url else [],
                )

            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                snippets=["No LinkedIn profile found"],
            )

        except ImportError:
            logger.warning("browser-use or langchain-openai not available, returning empty result")
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="browser-use or langchain-openai not installed",
            )

        except Exception as exc:
            logger.error("linkedin agent error: {}", str(exc))
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=f"LinkedIn agent error: {exc}",
            )


def _parse_linkedin_output(
    raw_output: str, person_name: str
) -> dict:
    """Parse browser-use output into structured profile data."""
    data: dict = {}
    try:
        # Try extracting JSON from the output
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw_output[start:end])
    except (json.JSONDecodeError, ValueError):
        logger.debug("linkedin: could not parse JSON from output, using raw text")

    profile_url = data.get("profile_url", "")
    display_name = data.get("full_name", person_name)
    headline = data.get("headline", "")
    location = data.get("location")
    about = data.get("about", "")
    current_company = data.get("current_company", "")
    current_title = data.get("current_title", "")
    experience = data.get("experience", [])
    education = data.get("education", [])
    skills = data.get("skills", [])
    connections = data.get("connections_count")
    recent_posts = data.get("recent_posts", [])

    # Build raw_data with all extracted fields
    raw_data = {
        "headline": headline,
        "about": about,
        "current_company": current_company,
        "current_title": current_title,
        "experience": experience,
        "education": education,
        "skills": skills,
        "connections_count": connections,
        "recent_posts": recent_posts,
        "browser_use_output": raw_output,
    }

    # Parse connections count to int if possible
    followers_count = None
    if connections:
        try:
            cleaned = str(connections).replace(",", "").replace("+", "").strip()
            followers_count = int(cleaned)
        except (ValueError, TypeError):
            pass

    profile = SocialProfile(
        platform="linkedin",
        url=profile_url if profile_url else f"https://linkedin.com/search?q={person_name}",
        display_name=display_name,
        bio=headline if headline else about[:200] if about else None,
        followers=followers_count,
        location=location,
        raw_data=raw_data,
    )

    snippets: list[str] = []
    if headline:
        snippets.append(f"LinkedIn: {display_name} — {headline}")
    if about:
        snippets.append(f"About: {about[:300]}")
    if experience:
        exp_strs = [
            f"{e.get('title', '?')} at {e.get('company', '?')}" for e in experience[:3]
        ]
        snippets.append(f"Experience: {'; '.join(exp_strs)}")
    if education:
        edu_strs = [
            f"{e.get('degree', '')} {e.get('field', '')} @ {e.get('school', '?')}"
            for e in education[:2]
        ]
        snippets.append(f"Education: {'; '.join(edu_strs)}")
    if skills:
        snippets.append(f"Skills: {', '.join(skills[:10])}")
    if recent_posts:
        for post in recent_posts[:2]:
            text = post.get("text", "")
            if text:
                snippets.append(f"Post: {text[:150]}")
    if not snippets:
        snippets.append(raw_output[:500])

    return {"profile": profile, "snippets": snippets}
