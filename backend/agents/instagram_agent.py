"""Instagram research agent using browser-use.

# RESEARCH: Checked instaloader (8k stars), instagram-private-api (archived), instagrapi (5k stars)
# DECISION: Browser Use — avoids API ban risk, works with login-gated content via cloud sessions
# ALT: instagrapi for heavier scraping needs (risk of account bans)
"""

from __future__ import annotations

import json

from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings


class InstagramAgent(BaseBrowserAgent):
    """Scrapes Instagram profiles via browser-use with authenticated session.

    Extracts: bio, post count, followers/following, recent posts, profile picture.
    """

    agent_name = "instagram"

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
        logger.info("instagram agent searching: {}", query)

        try:
            task = (
                f"Go to instagram.com and search for '{query}'. "
                f"Find the most likely Instagram profile for this person. "
                f"Click into their profile and extract ALL of the following in JSON format:\n"
                f'{{"username": "...", "display_name": "...", "bio": "...", '
                f'"followers": 0, "following": 0, "post_count": 0, '
                f'"is_verified": false, "is_private": false, '
                f'"recent_posts": [{{"caption": "...", "likes": 0, "date": "..."}}], '
                f'"profile_url": "..."}}\n'
                f"Return ONLY the JSON object, no other text."
            )

            agent = self._create_browser_agent(task)
            result = await agent.run()
            final_result = result.final_result() if result else None

            if final_result:
                parsed = _parse_instagram_output(str(final_result), request.person_name)
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
                snippets=["No Instagram profile found"],
            )

        except ImportError:
            logger.warning("browser-use or langchain-openai not available for instagram agent")
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="browser-use or langchain-openai not installed",
            )

        except Exception as exc:
            logger.error("instagram agent error: {}", str(exc))
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=f"Instagram agent error: {exc}",
            )


def _parse_instagram_output(raw_output: str, person_name: str) -> dict:
    """Parse browser-use output into structured Instagram profile data."""
    data: dict = {}
    try:
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw_output[start:end])
    except (json.JSONDecodeError, ValueError):
        logger.debug("instagram: could not parse JSON from output, using raw text")

    username = data.get("username", "")
    display_name = data.get("display_name", person_name)
    bio = data.get("bio", "")
    followers = data.get("followers")
    following = data.get("following")
    post_count = data.get("post_count")
    is_verified = data.get("is_verified", False)
    is_private = data.get("is_private", False)
    recent_posts = data.get("recent_posts", [])
    profile_url = data.get("profile_url", "")

    raw_data = {
        "post_count": post_count,
        "is_private": is_private,
        "recent_posts": recent_posts,
        "browser_use_output": raw_output,
    }

    profile = SocialProfile(
        platform="instagram",
        url=profile_url if profile_url else f"https://instagram.com/{username}" if username else "",
        username=username or None,
        display_name=display_name,
        bio=bio or None,
        followers=followers,
        following=following,
        verified=bool(is_verified),
        raw_data=raw_data,
    )

    snippets: list[str] = []
    if bio:
        snippets.append(
            f"@{username}: {bio}" if username else f"Instagram: {bio}"
        )
    if followers is not None:
        snippets.append(f"Followers: {followers:,}" if isinstance(followers, int) else "")
    if post_count is not None:
        snippets.append(f"Posts: {post_count}")
    if is_private:
        snippets.append("Account is private")
    if recent_posts:
        for post in recent_posts[:3]:
            caption = post.get("caption", "")
            if caption:
                snippets.append(f"Post: {caption[:150]}")
    if not snippets:
        snippets.append(raw_output[:500])

    snippets = [s for s in snippets if s]

    return {"profile": profile, "snippets": snippets}
