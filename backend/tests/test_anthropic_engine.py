from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from synthesis.anthropic_engine import AnthropicSynthesisEngine
from synthesis.models import SocialProfile, SynthesisRequest

MOCK_DOSSIER_JSON = json.dumps({
    "summary": "Elon Musk is CEO of Tesla and SpaceX, and owner of X (formerly Twitter).",
    "title": "CEO",
    "company": "Tesla / SpaceX",
    "work_history": [
        {"role": "CEO", "company": "Tesla", "period": "2008-present"},
        {"role": "CEO", "company": "SpaceX", "period": "2002-present"},
        {"role": "Owner", "company": "X (Twitter)", "period": "2022-present"},
    ],
    "education": [
        {"school": "University of Pennsylvania", "degree": "BS Economics, BS Physics"},
    ],
    "social_profiles": {
        "linkedin": "linkedin.com/in/elonmusk",
        "twitter": "@elonmusk",
        "instagram": None,
        "github": None,
        "website": "tesla.com",
    },
    "notable_activity": [
        "Starship orbital test flight in 2025",
        "Acquired Twitter and rebranded to X",
    ],
    "conversation_hooks": [
        "Ask about Starship progress",
        "Discuss Mars colonization timeline",
    ],
    "risk_flags": ["Controversial public statements on social media"],
})


# ── Configuration Tests ──


def test_anthropic_engine_not_configured() -> None:
    engine = AnthropicSynthesisEngine(Settings(ANTHROPIC_API_KEY=""))
    assert engine.configured is False


def test_anthropic_engine_configured() -> None:
    engine = AnthropicSynthesisEngine(Settings(ANTHROPIC_API_KEY="sk-test-123"))
    assert engine.configured is True


# ── Synthesis Tests (mocked) ──


@pytest.mark.anyio
async def test_anthropic_synthesize_unconfigured() -> None:
    engine = AnthropicSynthesisEngine(Settings(ANTHROPIC_API_KEY=""))
    result = await engine.synthesize(SynthesisRequest(person_name="Test"))
    assert result.success is False
    assert "not configured" in result.error


@pytest.mark.anyio
async def test_anthropic_synthesize_success() -> None:
    settings = Settings(ANTHROPIC_API_KEY="sk-test-123")
    engine = AnthropicSynthesisEngine(settings)

    # Mock the Anthropic client
    mock_content_block = MagicMock()
    mock_content_block.text = MOCK_DOSSIER_JSON

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    engine._client = mock_client

    request = SynthesisRequest(
        person_name="Elon Musk",
        enrichment_snippets=["CEO of Tesla", "Founder of SpaceX"],
        social_profiles=[
            SocialProfile(platform="twitter", url="https://x.com/elonmusk", username="@elonmusk"),
        ],
    )

    result = await engine.synthesize(request)

    assert result.success is True
    assert result.person_name == "Elon Musk"
    assert result.occupation == "CEO"
    assert result.organization == "Tesla / SpaceX"
    assert result.confidence_score == 0.75
    assert result.dossier is not None
    assert "Tesla" in result.dossier.summary
    assert len(result.dossier.work_history) == 3
    assert result.dossier.work_history[0].company == "Tesla"
    assert len(result.dossier.education) == 1
    assert result.dossier.social_profiles.twitter == "@elonmusk"
    assert len(result.dossier.conversation_hooks) == 2
    assert len(result.dossier.risk_flags) == 1

    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-20250514"
    assert call_kwargs["max_tokens"] == 4096


@pytest.mark.anyio
async def test_anthropic_synthesize_empty_response() -> None:
    settings = Settings(ANTHROPIC_API_KEY="sk-test-123")
    engine = AnthropicSynthesisEngine(settings)

    mock_response = MagicMock()
    mock_response.content = []

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Test"))

    assert result.success is False
    assert "empty response" in result.error


@pytest.mark.anyio
async def test_anthropic_synthesize_invalid_json() -> None:
    settings = Settings(ANTHROPIC_API_KEY="sk-test-123")
    engine = AnthropicSynthesisEngine(settings)

    mock_content_block = MagicMock()
    mock_content_block.text = "This is definitely not JSON"

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Test"))

    assert result.success is False
    assert "not valid JSON" in result.error


@pytest.mark.anyio
async def test_anthropic_synthesize_markdown_fenced_json() -> None:
    """Claude sometimes wraps JSON in markdown code fences."""
    settings = Settings(ANTHROPIC_API_KEY="sk-test-123")
    engine = AnthropicSynthesisEngine(settings)

    fenced = f"```json\n{MOCK_DOSSIER_JSON}\n```"
    mock_content_block = MagicMock()
    mock_content_block.text = fenced

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Elon Musk"))

    assert result.success is True
    assert result.dossier is not None
    assert result.dossier.title == "CEO"


@pytest.mark.anyio
async def test_anthropic_synthesize_api_error() -> None:
    settings = Settings(ANTHROPIC_API_KEY="sk-test-123")
    engine = AnthropicSynthesisEngine(settings)

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("429 rate limit exceeded"))
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Test"))

    assert result.success is False
    assert "429" in result.error


@pytest.mark.anyio
async def test_anthropic_synthesize_partial_data() -> None:
    """Engine should handle minimal/partial data gracefully."""
    settings = Settings(ANTHROPIC_API_KEY="sk-test-123")
    engine = AnthropicSynthesisEngine(settings)

    minimal_json = json.dumps({
        "summary": "Unknown person with limited data.",
        "title": None,
        "company": None,
        "work_history": [],
        "education": [],
        "social_profiles": {},
        "notable_activity": [],
        "conversation_hooks": [],
        "risk_flags": [],
    })

    mock_content_block = MagicMock()
    mock_content_block.text = minimal_json

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]

    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Nobody"))

    assert result.success is True
    assert result.dossier is not None
    assert result.dossier.summary == "Unknown person with limited data."
    assert result.dossier.work_history == []
    assert result.dossier.education == []


# ── Raw Data Block Builder Tests ──


def test_build_raw_data_block_empty() -> None:
    engine = AnthropicSynthesisEngine(Settings())
    request = SynthesisRequest(person_name="Empty")
    block = engine._build_raw_data_block(request)
    assert "No data available" in block


def test_build_raw_data_block_with_all_sources() -> None:
    engine = AnthropicSynthesisEngine(Settings())
    request = SynthesisRequest(
        person_name="Alice",
        face_search_urls=["https://pimeyes.com/result/1"],
        enrichment_snippets=["Engineer at Google"],
        social_profiles=[
            SocialProfile(
                platform="twitter", url="https://x.com/alice",
                username="@alice", bio="Building AI",
            ),
        ],
        raw_agent_data={"linkedin": "Alice works at Google"},
    )
    block = engine._build_raw_data_block(request)
    assert "Face Search URLs" in block
    assert "pimeyes.com" in block
    assert "Enrichment Results" in block
    assert "Engineer at Google" in block
    assert "Known Social Profiles" in block
    assert "@alice" in block
    assert "Building AI" in block
    assert "linkedin Agent Data" in block


# ── Parse Response Tests ──


def test_parse_response_valid() -> None:
    engine = AnthropicSynthesisEngine(Settings())
    dossier = engine._parse_response(MOCK_DOSSIER_JSON, "Elon Musk")
    assert dossier.title == "CEO"
    assert dossier.company == "Tesla / SpaceX"
    assert len(dossier.work_history) == 3
    assert len(dossier.education) == 1
    assert dossier.social_profiles.twitter == "@elonmusk"


def test_parse_response_with_markdown_fences() -> None:
    engine = AnthropicSynthesisEngine(Settings())
    fenced = f"```json\n{MOCK_DOSSIER_JSON}\n```"
    dossier = engine._parse_response(fenced, "Elon Musk")
    assert dossier.title == "CEO"


def test_parse_response_filters_empty_entries() -> None:
    engine = AnthropicSynthesisEngine(Settings())
    data = json.dumps({
        "summary": "Test",
        "title": "Eng",
        "company": "Co",
        "work_history": [
            {"role": "Eng", "company": "Co"},
            {"role": "", "company": ""},
        ],
        "education": [
            {"school": "MIT"},
            {"school": ""},
        ],
        "social_profiles": {},
        "notable_activity": [],
        "conversation_hooks": [],
        "risk_flags": [],
    })
    dossier = engine._parse_response(data, "Test")
    assert len(dossier.work_history) == 1
    assert len(dossier.education) == 1


# ── Fallback Integration Test (pipeline-level) ──


@pytest.mark.anyio
async def test_pipeline_fallback_from_gemini_to_anthropic() -> None:
    """When Gemini returns a 429, the pipeline should fall back to Anthropic."""
    from synthesis.engine import GeminiSynthesisEngine
    from synthesis.models import SynthesisResult

    gemini_settings = Settings(GEMINI_API_KEY="test-gemini")
    anthropic_settings = Settings(ANTHROPIC_API_KEY="test-anthropic")

    gemini_engine = GeminiSynthesisEngine(gemini_settings)
    anthropic_engine = AnthropicSynthesisEngine(anthropic_settings)

    # Gemini returns 429
    gemini_result = SynthesisResult(
        person_name="Test",
        success=False,
        error="429 Resource has been exhausted",
    )

    # Anthropic returns success
    anthropic_result = SynthesisResult(
        person_name="Test",
        summary="Test person summary",
        success=True,
        confidence_score=0.75,
    )

    with (
        patch.object(gemini_engine, "synthesize", return_value=gemini_result) as mock_gemini,
        patch.object(
            anthropic_engine, "synthesize", return_value=anthropic_result
        ) as mock_anthropic,
    ):
        request = SynthesisRequest(person_name="Test Person")

        # Simulate pipeline logic
        result = await gemini_engine.synthesize(request)

        if (
            not result.success
            and result.error
            and "429" in result.error
            and anthropic_engine.configured
        ):
            result = await anthropic_engine.synthesize(request)

        assert result.success is True
        assert result.summary == "Test person summary"
        mock_gemini.assert_called_once()
        mock_anthropic.assert_called_once()


@pytest.mark.anyio
async def test_pipeline_fallback_on_any_primary_failure() -> None:
    """Any primary engine failure should trigger the fallback (not just 429)."""
    from synthesis.engine import GeminiSynthesisEngine
    from synthesis.models import SynthesisResult

    anthropic_settings = Settings(ANTHROPIC_API_KEY="test-anthropic")
    gemini_settings = Settings(GEMINI_API_KEY="test-gemini")

    # Anthropic is now primary, Gemini is fallback
    primary = AnthropicSynthesisEngine(anthropic_settings)
    fallback = GeminiSynthesisEngine(gemini_settings)

    primary_result = SynthesisResult(
        person_name="Test",
        success=False,
        error="Invalid JSON response from model",
    )

    fallback_result = SynthesisResult(
        person_name="Test",
        summary="Recovered via fallback",
        success=True,
        confidence_score=0.7,
    )

    with (
        patch.object(primary, "synthesize", return_value=primary_result) as mock_primary,
        patch.object(fallback, "synthesize", return_value=fallback_result) as mock_fallback,
    ):
        request = SynthesisRequest(person_name="Test Person")
        result = await primary.synthesize(request)

        # Generalized fallback: any failure triggers fallback
        if not result.success and fallback.configured:
            result = await fallback.synthesize(request)

        assert result.success is True
        assert result.summary == "Recovered via fallback"
        mock_primary.assert_called_once()
        mock_fallback.assert_called_once()
