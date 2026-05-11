"""Tests for browser research agents.

Tests cover:
- Pydantic models shape validation
- Base agent timeout and error handling
- Individual agent unconfigured behavior
- OSINT, Darkweb, and Social agent behavior
- Orchestrator fan-out with mocked agents
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from agents.browser_agent import BaseBrowserAgent
from agents.darkweb_agent import DarkwebAgent
from agents.google_agent import GoogleAgent
from agents.instagram_agent import InstagramAgent, _parse_instagram_output
from agents.linkedin_agent import LinkedInAgent, _parse_linkedin_output
from agents.models import (
    AgentResult,
    AgentStatus,
    OrchestratorResult,
    ResearchRequest,
    SocialProfile,
)
from agents.orchestrator import ResearchOrchestrator, _deduplicate_profiles
from agents.osint_agent import OsintAgent
from agents.social_agent import SocialAgent
from agents.twitter_agent import TwitterAgent, _parse_twitter_output
from config import Settings

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def unconfigured_settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        OPENAI_API_KEY=None,
        BROWSER_USE_API_KEY=None,
        HIBP_API_KEY=None,
    )


@pytest.fixture()
def configured_settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        OPENAI_API_KEY="sk-test-key",
        BROWSER_USE_API_KEY="bu-test-key",
        HIBP_API_KEY="hibp-test-key",
    )


@pytest.fixture()
def research_request() -> ResearchRequest:
    return ResearchRequest(
        person_name="John Doe",
        company="Acme Corp",
        timeout_seconds=5.0,
    )


# ── Model Tests ──────────────────────────────────────────────────────────────


class TestAgentModels:
    def test_social_profile_minimal(self) -> None:
        profile = SocialProfile(platform="twitter", url="https://x.com/test")
        assert profile.platform == "twitter"
        assert profile.username is None
        assert profile.verified is False

    def test_social_profile_full(self) -> None:
        profile = SocialProfile(
            platform="linkedin",
            url="https://linkedin.com/in/test",
            username="test",
            display_name="Test User",
            bio="Engineer",
            followers=1000,
            following=500,
            location="SF",
            verified=True,
            raw_data={"key": "value"},
        )
        assert profile.followers == 1000
        assert profile.verified is True

    def test_agent_result_defaults(self) -> None:
        result = AgentResult(agent_name="test")
        assert result.status == AgentStatus.PENDING
        assert result.profiles == []
        assert result.snippets == []
        assert result.error is None

    def test_agent_result_with_data(self) -> None:
        result = AgentResult(
            agent_name="linkedin",
            status=AgentStatus.SUCCESS,
            profiles=[SocialProfile(platform="linkedin", url="https://linkedin.com/in/test")],
            snippets=["Engineer at Acme"],
        )
        assert len(result.profiles) == 1
        assert result.status == AgentStatus.SUCCESS

    def test_research_request_defaults(self) -> None:
        req = ResearchRequest(person_name="Jane Doe")
        assert req.company is None
        assert req.timeout_seconds == 90.0
        assert req.face_search_urls == []

    def test_research_request_full(self) -> None:
        req = ResearchRequest(
            person_name="Jane Doe",
            company="BigCo",
            face_search_urls=["https://example.com/face.jpg"],
            additional_context="CEO",
            timeout_seconds=60.0,
        )
        assert req.timeout_seconds == 60.0

    def test_orchestrator_result_defaults(self) -> None:
        result = OrchestratorResult(person_name="Test")
        assert result.agent_results == {}
        assert result.all_profiles == []
        assert result.success is True

    def test_agent_status_enum(self) -> None:
        assert AgentStatus.PENDING.value == "pending"
        assert AgentStatus.RUNNING.value == "running"
        assert AgentStatus.SUCCESS.value == "success"
        assert AgentStatus.FAILED.value == "failed"
        assert AgentStatus.TIMEOUT.value == "timeout"


# ── Base Agent Tests ─────────────────────────────────────────────────────────


class _TestAgent(BaseBrowserAgent):
    """Concrete subclass for testing the base agent."""

    agent_name = "test_agent"

    def __init__(self, settings: Settings, behavior: str = "success"):
        super().__init__(settings)
        self._behavior = behavior

    async def _run_task(self, request: ResearchRequest) -> AgentResult:
        if self._behavior == "success":
            return AgentResult(
                agent_name=self.agent_name,
                status=AgentStatus.SUCCESS,
                snippets=["Found data"],
            )
        elif self._behavior == "error":
            raise ValueError("Something went wrong")
        elif self._behavior == "slow":
            await asyncio.sleep(30)
            return AgentResult(agent_name=self.agent_name, status=AgentStatus.SUCCESS)
        return AgentResult(agent_name=self.agent_name, status=AgentStatus.FAILED)


class TestBaseBrowserAgent:
    def test_configured_with_openai_key(self, configured_settings: Settings) -> None:
        agent = _TestAgent(configured_settings)
        assert agent.configured is True

    def test_not_configured_without_keys(self, unconfigured_settings: Settings) -> None:
        agent = _TestAgent(unconfigured_settings)
        assert agent.configured is False

    def test_successful_run(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = _TestAgent(configured_settings, behavior="success")
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.SUCCESS
        assert result.duration_seconds > 0
        assert result.completed_at is not None

    def test_error_isolation(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = _TestAgent(configured_settings, behavior="error")
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.FAILED
        assert "Something went wrong" in result.error

    def test_timeout_handling(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        request = research_request.model_copy(update={"timeout_seconds": 0.1})
        agent = _TestAgent(configured_settings, behavior="slow")
        result = asyncio.run(agent.run(request))
        assert result.status == AgentStatus.TIMEOUT
        assert "timed out" in result.error

    def test_build_search_query_name_only(self, configured_settings: Settings) -> None:
        agent = _TestAgent(configured_settings)
        req = ResearchRequest(person_name="John Doe")
        assert agent._build_search_query(req) == "John Doe"

    def test_build_search_query_with_company(self, configured_settings: Settings) -> None:
        agent = _TestAgent(configured_settings)
        req = ResearchRequest(person_name="John Doe", company="Acme")
        assert agent._build_search_query(req) == "John Doe Acme"


# ── Individual Agent Tests ───────────────────────────────────────────────────


class TestLinkedInAgent:
    def test_fails_when_unconfigured(
        self, unconfigured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = LinkedInAgent(unconfigured_settings)
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.FAILED
        assert "not configured" in result.error

    def test_agent_name(self, configured_settings: Settings) -> None:
        agent = LinkedInAgent(configured_settings)
        assert agent.agent_name == "linkedin"


class TestTwitterAgent:
    def test_agent_name(self, configured_settings: Settings) -> None:
        agent = TwitterAgent(configured_settings)
        assert agent.agent_name == "twitter"

    def test_falls_through_when_unconfigured(
        self, unconfigured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = TwitterAgent(unconfigured_settings)
        result = asyncio.run(agent.run(research_request))
        # twscrape may fail, then browser-use fallback fails due to no config
        assert result.status in {AgentStatus.FAILED, AgentStatus.SUCCESS}


class TestGoogleAgent:
    def test_fails_when_unconfigured(
        self, unconfigured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = GoogleAgent(unconfigured_settings)
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.FAILED
        assert "not configured" in result.error

    def test_agent_name(self, configured_settings: Settings) -> None:
        agent = GoogleAgent(configured_settings)
        assert agent.agent_name == "google"


# ── OSINT Agent Tests ────────────────────────────────────────────────────────


class TestOsintAgent:
    def test_fails_when_unconfigured(
        self, unconfigured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = OsintAgent(unconfigured_settings)
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.FAILED
        assert "not configured" in result.error

    def test_agent_name(self, configured_settings: Settings) -> None:
        agent = OsintAgent(configured_settings)
        assert agent.agent_name == "osint"

    def test_configured_with_keys(self, configured_settings: Settings) -> None:
        agent = OsintAgent(configured_settings)
        assert agent.configured is True


# ── Darkweb Agent Tests ──────────────────────────────────────────────────────


class TestDarkwebAgent:
    def test_fails_when_unconfigured(
        self, unconfigured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = DarkwebAgent(unconfigured_settings)
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.FAILED
        assert "HIBP_API_KEY" in result.error

    def test_agent_name(self, configured_settings: Settings) -> None:
        agent = DarkwebAgent(configured_settings)
        assert agent.agent_name == "darkweb"

    def test_configured_with_hibp_key(self, configured_settings: Settings) -> None:
        agent = DarkwebAgent(configured_settings)
        assert agent.configured is True

    def test_not_configured_without_hibp_key(self, unconfigured_settings: Settings) -> None:
        agent = DarkwebAgent(unconfigured_settings)
        assert agent.configured is False

    def test_guess_emails_with_company(self, configured_settings: Settings) -> None:
        agent = DarkwebAgent(configured_settings)
        req = ResearchRequest(person_name="John Doe", company="Acme Corp")
        emails = agent._guess_emails(req)
        assert "john.doe@acmecorp.com" in emails
        assert "jdoe@acmecorp.com" in emails
        assert "john.doe@gmail.com" in emails

    def test_guess_emails_no_company(self, configured_settings: Settings) -> None:
        agent = DarkwebAgent(configured_settings)
        req = ResearchRequest(person_name="John Doe")
        emails = agent._guess_emails(req)
        assert "john.doe@gmail.com" in emails
        assert "johndoe@gmail.com" in emails
        # No company-domain emails
        assert all("acme" not in e for e in emails)

    def test_guess_emails_single_name(self, configured_settings: Settings) -> None:
        agent = DarkwebAgent(configured_settings)
        req = ResearchRequest(person_name="Madonna")
        emails = agent._guess_emails(req)
        assert emails == []

    def test_hibp_success_with_mocked_response(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = DarkwebAgent(configured_settings)

        mock_breaches = [
            {"Name": "Adobe", "BreachDate": "2013-10-04", "Domain": "adobe.com"},
            {"Name": "LinkedIn", "BreachDate": "2012-05-05", "Domain": "linkedin.com"},
        ]

        mock_response = httpx.Response(
            status_code=200,
            json=mock_breaches,
            request=httpx.Request("GET", "https://test"),
        )

        with patch("agents.darkweb_agent.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(agent.run(research_request))
            assert result.status == AgentStatus.SUCCESS
            assert len(result.snippets) > 0
            assert any("breach" in s.lower() or "Adobe" in s for s in result.snippets)

    def test_hibp_404_no_breaches(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = DarkwebAgent(configured_settings)

        mock_response = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://test"),
        )

        with patch("agents.darkweb_agent.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(agent.run(research_request))
            assert result.status == AgentStatus.SUCCESS
            assert any("No breaches" in s or "no results" in s.lower() for s in result.snippets)


# ── Instagram Agent Tests ────────────────────────────────────────────────────


class TestInstagramAgent:
    def test_fails_when_unconfigured(
        self, unconfigured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = InstagramAgent(unconfigured_settings)
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.FAILED
        assert "not configured" in result.error

    def test_agent_name(self, configured_settings: Settings) -> None:
        agent = InstagramAgent(configured_settings)
        assert agent.agent_name == "instagram"

    def test_configured_with_keys(self, configured_settings: Settings) -> None:
        agent = InstagramAgent(configured_settings)
        assert agent.configured is True


# ── LinkedIn Parser Tests ───────────────────────────────────────────────────


class TestLinkedInParser:
    def test_parse_valid_json(self) -> None:
        import json

        data = {
            "full_name": "Jane Doe",
            "headline": "CEO at BigCo",
            "location": "SF",
            "about": "Builder.",
            "current_company": "BigCo",
            "current_title": "CEO",
            "experience": [{"title": "CEO", "company": "BigCo", "duration": "2y"}],
            "education": [{"school": "MIT", "degree": "BS", "field": "CS"}],
            "skills": ["Python", "Leadership"],
            "connections_count": "500+",
            "recent_posts": [{"text": "Launched v2!", "date": "2026-02-01"}],
            "profile_url": "https://linkedin.com/in/janedoe",
        }
        raw = json.dumps(data)
        result = _parse_linkedin_output(raw, "Jane Doe")
        assert result["profile"].platform == "linkedin"
        assert result["profile"].display_name == "Jane Doe"
        assert result["profile"].url == "https://linkedin.com/in/janedoe"
        assert result["profile"].bio == "CEO at BigCo"
        assert result["profile"].followers == 500
        assert len(result["snippets"]) > 0

    def test_parse_invalid_json_falls_back(self) -> None:
        raw = "Some random text about the person"
        result = _parse_linkedin_output(raw, "John Doe")
        assert result["profile"].platform == "linkedin"
        assert result["profile"].display_name == "John Doe"
        assert len(result["snippets"]) > 0
        assert raw[:500] in result["snippets"][0]

    def test_parse_empty_json(self) -> None:
        raw = "{}"
        result = _parse_linkedin_output(raw, "Test")
        assert result["profile"].platform == "linkedin"
        assert result["profile"].display_name == "Test"


# ── Twitter Parser Tests ────────────────────────────────────────────────────


class TestTwitterParser:
    def test_parse_valid_json(self) -> None:
        import json

        data = {
            "username": "johndoe",
            "display_name": "John Doe",
            "bio": "Builder of things",
            "followers": 1500,
            "following": 300,
            "tweets_count": 5000,
            "location": "SF",
            "verified": True,
            "recent_tweets": [{"text": "Hello world", "date": "2026-02-01", "likes": 42}],
            "interests": ["tech", "AI"],
            "profile_url": "https://x.com/johndoe",
        }
        raw = json.dumps(data)
        result = _parse_twitter_output(raw, "John Doe")
        assert result["profile"].platform == "twitter"
        assert result["profile"].username == "johndoe"
        assert result["profile"].followers == 1500
        assert result["profile"].verified is True
        assert len(result["snippets"]) > 0

    def test_parse_invalid_json_falls_back(self) -> None:
        raw = "Could not find the profile"
        result = _parse_twitter_output(raw, "John Doe")
        assert result["profile"].platform == "twitter"
        assert result["profile"].display_name == "John Doe"
        assert len(result["snippets"]) > 0

    def test_parse_empty_json(self) -> None:
        raw = "{}"
        result = _parse_twitter_output(raw, "Test")
        assert result["profile"].platform == "twitter"
        assert result["profile"].display_name == "Test"


# ── Instagram Parser Tests ──────────────────────────────────────────────────


class TestInstagramParser:
    def test_parse_valid_json(self) -> None:
        import json

        data = {
            "username": "janedoe",
            "display_name": "Jane Doe",
            "bio": "Photographer",
            "followers": 10000,
            "following": 500,
            "post_count": 150,
            "is_verified": False,
            "is_private": False,
            "recent_posts": [
                {"caption": "Sunset shot", "likes": 200, "date": "2026-02-01"}
            ],
            "profile_url": "https://instagram.com/janedoe",
        }
        raw = json.dumps(data)
        result = _parse_instagram_output(raw, "Jane Doe")
        assert result["profile"].platform == "instagram"
        assert result["profile"].username == "janedoe"
        assert result["profile"].followers == 10000
        assert len(result["snippets"]) > 0

    def test_parse_invalid_json_falls_back(self) -> None:
        raw = "No profile found"
        result = _parse_instagram_output(raw, "Jane Doe")
        assert result["profile"].platform == "instagram"
        assert len(result["snippets"]) > 0

    def test_parse_private_account(self) -> None:
        raw = '{"username": "private_user", "is_private": true, "bio": "Private life"}'
        result = _parse_instagram_output(raw, "Private User")
        assert any("private" in s.lower() for s in result["snippets"])


# ── Social Agent Tests ───────────────────────────────────────────────────────


class TestSocialAgent:
    def test_fails_when_unconfigured(
        self, unconfigured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        agent = SocialAgent(unconfigured_settings)
        result = asyncio.run(agent.run(research_request))
        assert result.status == AgentStatus.FAILED
        assert "configured" in result.error

    def test_agent_name(self, configured_settings: Settings) -> None:
        agent = SocialAgent(configured_settings)
        assert agent.agent_name == "social"

    def test_configured_with_keys(self, configured_settings: Settings) -> None:
        agent = SocialAgent(configured_settings)
        assert agent.configured is True


# ── Orchestrator Tests ───────────────────────────────────────────────────────


class TestOrchestrator:
    def test_agent_names(self, configured_settings: Settings) -> None:
        orchestrator = ResearchOrchestrator(configured_settings)
        assert "linkedin" in orchestrator.agent_names
        assert "twitter" in orchestrator.agent_names
        assert "google" in orchestrator.agent_names
        assert "instagram" in orchestrator.agent_names
        assert "osint" in orchestrator.agent_names
        assert "darkweb" in orchestrator.agent_names
        assert "social" in orchestrator.agent_names

    def test_research_with_all_agents_mocked(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        orchestrator = ResearchOrchestrator(configured_settings)

        mock_result = AgentResult(
            agent_name="mock",
            status=AgentStatus.SUCCESS,
            profiles=[SocialProfile(platform="test", url="https://test.com")],
            snippets=["test snippet"],
        )

        for agent in orchestrator._static_agents:
            agent.run = AsyncMock(return_value=mock_result)  # type: ignore[method-assign]

        result = asyncio.run(orchestrator.research_person(research_request))
        assert isinstance(result, OrchestratorResult)
        assert result.success is True
        assert result.person_name == "John Doe"
        assert len(result.all_profiles) > 0
        assert len(result.all_snippets) > 0
        assert result.total_duration_seconds > 0

    def test_research_handles_agent_exception(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        orchestrator = ResearchOrchestrator(configured_settings)

        success_result = AgentResult(
            agent_name="mock",
            status=AgentStatus.SUCCESS,
            snippets=["data"],
        )

        # First agent raises, all others succeed
        orchestrator._static_agents[0].run = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("boom")
        )
        for agent in orchestrator._static_agents[1:]:
            agent.run = AsyncMock(return_value=success_result)  # type: ignore[method-assign]

        result = asyncio.run(orchestrator.research_person(research_request))
        assert result.success is True  # Other agents still succeeded
        # The failed agent should have a FAILED status
        failed_agents = [
            r for r in result.agent_results.values() if r.status == AgentStatus.FAILED
        ]
        assert len(failed_agents) == 1

    def test_research_all_fail(
        self, configured_settings: Settings, research_request: ResearchRequest
    ) -> None:
        orchestrator = ResearchOrchestrator(configured_settings)

        fail_result = AgentResult(
            agent_name="mock",
            status=AgentStatus.FAILED,
            error="fail",
        )

        for agent in orchestrator._static_agents:
            agent.run = AsyncMock(return_value=fail_result)  # type: ignore[method-assign]

        result = asyncio.run(orchestrator.research_person(research_request))
        assert result.success is False
        assert result.error == "All agents failed"


# ── Utility Tests ────────────────────────────────────────────────────────────


class TestDeduplicateProfiles:
    def test_removes_duplicates(self) -> None:
        profiles = [
            SocialProfile(platform="twitter", url="https://x.com/test"),
            SocialProfile(platform="twitter", url="https://x.com/test"),
            SocialProfile(platform="linkedin", url="https://linkedin.com/in/test"),
        ]
        result = _deduplicate_profiles(profiles)
        assert len(result) == 2

    def test_preserves_unique(self) -> None:
        profiles = [
            SocialProfile(platform="twitter", url="https://x.com/a"),
            SocialProfile(platform="twitter", url="https://x.com/b"),
        ]
        result = _deduplicate_profiles(profiles)
        assert len(result) == 2

    def test_empty_list(self) -> None:
        assert _deduplicate_profiles([]) == []
