"""Twitter/X research agent using twscrape with browser-use fallback.

# RESEARCH: Checked twscrape (2.5k stars, updated Jan 2026), tweepy (10k stars, API v2 only)
# DECISION: twscrape primary (reverse GraphQL, no API key needed), browser-use fallback
# ALT: tweepy requires paid API access ($100/mo minimum)
"""

from __future__ import annotations

import json

from loguru import logger

from agents.browser_agent import BaseBrowserAgent
from agents.models import AgentResult, AgentStatus, ResearchRequest, SocialProfile
from config import Settings


class TwitterAgent(BaseBrowserAgent):
    """Scrapes Twitter/X profiles using twscrape, falls back to browser-use.

    Extracts: bio, tweets, followers/following, interests, verified status.
    twscrape uses reverse-engineered GraphQL (no API key needed).
    """

    agent_name = "twitter"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    async def _run_task(self, request: ResearchRequest) -> AgentResult:
        # Try twscrape first (faster, no browser needed)
        twscrape_result = await self._try_twscrape(request)
        if twscrape_result and twscrape_result.status == AgentStatus.SUCCESS:
            return twscrape_result

        # Fallback to browser-use
        logger.info("twscrape failed or empty, falling back to browser-use for twitter")
        return await self._try_browser_use(request)

    async def _try_twscrape(self, request: ResearchRequest) -> AgentResult | None:
        try:
            from twscrape import API

            api = API()
            query = self._build_search_query(request)
            logger.info("twitter twscrape searching: {}", query)

            profiles: list[SocialProfile] = []
            snippets: list[str] = []

            users = []
            async for user in api.search(query, limit=5):
                users.append(user)

            if not users:
                return None

            for user in users[:3]:
                user_dict = user.dict() if hasattr(user, "dict") else {}
                username = user_dict.get("username", "")
                display_name = user_dict.get("displayname", "")
                bio = user_dict.get("rawDescription", "")
                followers = user_dict.get("followersCount", 0)
                following = user_dict.get("friendsCount", 0)
                location = user_dict.get("location", "")
                verified = user_dict.get("verified", False) or user_dict.get("blue", False)
                tweets_count = user_dict.get("statusesCount", 0)
                created = user_dict.get("created")

                raw_data = {
                    **user_dict,
                    "tweets_count": tweets_count,
                    "account_created": str(created) if created else None,
                }

                profile = SocialProfile(
                    platform="twitter",
                    url=f"https://x.com/{username}" if username else "",
                    username=username,
                    display_name=display_name,
                    bio=bio,
                    followers=followers if followers else None,
                    following=following if following else None,
                    location=location or None,
                    verified=verified,
                    raw_data=raw_data,
                )
                profiles.append(profile)

                if bio:
                    snippets.append(f"@{username}: {bio}")
                if tweets_count:
                    snippets.append(f"@{username} tweets: {tweets_count}")

            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                profiles=profiles,
                snippets=snippets,
                urls_found=[p.url for p in profiles if p.url],
            )

        except ImportError:
            logger.warning("twscrape not available")
            return None

        except Exception as exc:
            logger.warning("twscrape search failed: {}", str(exc))
            return None

    async def _try_browser_use(self, request: ResearchRequest) -> AgentResult:
        if not self.configured:
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="Neither twscrape nor Browser Use available",
            )

        try:
            query = self._build_search_query(request)
            task = (
                f"Go to x.com and search for '{query}'. "
                f"Find the most likely Twitter/X profile for this person. "
                f"Click into their profile and extract ALL of the following in JSON format:\n"
                f'{{"username": "...", "display_name": "...", "bio": "...", '
                f'"followers": 0, "following": 0, "tweets_count": 0, '
                f'"location": "...", "verified": false, '
                f'"recent_tweets": [{{"text": "...", "date": "...", "likes": 0}}], '
                f'"interests": ["..."], "profile_url": "..."}}\n'
                f"Return ONLY the JSON object, no other text."
            )

            agent = self._create_browser_agent(task)
            result = await agent.run()
            final_result = result.final_result() if result else None

            if final_result:
                parsed = _parse_twitter_output(str(final_result), request.person_name)
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
                snippets=["No Twitter profile found"],
            )

        except ImportError:
            logger.warning("browser-use or langchain-openai not available for twitter fallback")
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error="browser-use or langchain-openai not installed",
            )

        except Exception as exc:
            logger.error("twitter browser-use fallback error: {}", str(exc))
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=f"Twitter browser fallback error: {exc}",
            )


def _parse_twitter_output(raw_output: str, person_name: str) -> dict:
    """Parse browser-use output into structured Twitter profile data."""
    data: dict = {}
    try:
        start = raw_output.find("{")
        end = raw_output.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw_output[start:end])
    except (json.JSONDecodeError, ValueError):
        logger.debug("twitter: could not parse JSON from output, using raw text")

    username = data.get("username", "")
    display_name = data.get("display_name", person_name)
    bio = data.get("bio", "")
    followers = data.get("followers")
    following = data.get("following")
    tweets_count = data.get("tweets_count")
    location = data.get("location")
    verified = data.get("verified", False)
    recent_tweets = data.get("recent_tweets", [])
    interests = data.get("interests", [])
    profile_url = data.get("profile_url", "")

    raw_data = {
        "tweets_count": tweets_count,
        "recent_tweets": recent_tweets,
        "interests": interests,
        "browser_use_output": raw_output,
    }

    profile = SocialProfile(
        platform="twitter",
        url=profile_url if profile_url else f"https://x.com/search?q={person_name}",
        username=username or None,
        display_name=display_name,
        bio=bio or None,
        followers=followers,
        following=following,
        location=location or None,
        verified=bool(verified),
        raw_data=raw_data,
    )

    snippets: list[str] = []
    if bio:
        snippets.append(f"@{username}: {bio}" if username else f"Twitter: {bio}")
    if followers is not None:
        snippets.append(f"Followers: {followers:,}" if isinstance(followers, int) else "")
    if recent_tweets:
        for tweet in recent_tweets[:3]:
            text = tweet.get("text", "")
            if text:
                snippets.append(f"Tweet: {text[:150]}")
    if interests:
        snippets.append(f"Interests: {', '.join(interests[:8])}")
    if not snippets:
        snippets.append(raw_output[:500])

    # Filter empty strings
    snippets = [s for s in snippets if s]

    return {"profile": profile, "snippets": snippets}
