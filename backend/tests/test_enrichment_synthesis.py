from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import Settings
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest
from synthesis.engine import GeminiSynthesisEngine
from synthesis.models import SocialProfile, SynthesisRequest

# ── Fixtures ──


MOCK_EXA_RESULTS = [
    SimpleNamespace(
        title="Alice Smith - LinkedIn",
        url="https://linkedin.com/in/alicesmith",
        text="Alice Smith is a software engineer at Google. Previously at Meta.",
        highlights=["software engineer at Google", "Previously at Meta"],
        score=0.92,
    ),
    SimpleNamespace(
        title="Alice Smith (@alice) / X",
        url="https://x.com/alice",
        text="AI researcher. Building cool things. Stanford PhD.",
        highlights=["AI researcher", "Stanford PhD"],
        score=0.85,
    ),
]

MOCK_GEMINI_RESPONSE_JSON = json.dumps({
    "summary": "Alice Smith is a software engineer at Google, previously at Meta. Stanford PhD.",
    "title": "Software Engineer",
    "company": "Google",
    "work_history": [
        {"role": "Software Engineer", "company": "Google", "period": "2022-present"},
        {"role": "Software Engineer", "company": "Meta", "period": "2019-2022"},
    ],
    "education": [
        {"school": "Stanford University", "degree": "PhD Computer Science"},
    ],
    "social_profiles": {
        "linkedin": "linkedin.com/in/alicesmith",
        "twitter": "@alice",
        "instagram": None,
        "github": "github.com/alicesmith",
        "website": None,
    },
    "notable_activity": ["Published paper on LLM safety at NeurIPS 2025"],
    "conversation_hooks": [
        "Ask about her NeurIPS paper on LLM safety",
        "Discuss the transition from Meta to Google",
    ],
    "risk_flags": [],
})


# ── Exa Client Tests ──


def test_exa_client_not_configured() -> None:
    client = ExaEnrichmentClient(Settings())
    assert client.configured is False


def test_exa_client_configured() -> None:
    client = ExaEnrichmentClient(Settings(EXA_API_KEY="test-key"))
    assert client.configured is True


def test_exa_build_query_name_only() -> None:
    client = ExaEnrichmentClient(Settings())
    assert client.build_person_query("John Doe") == '"John Doe"'


def test_exa_build_query_with_company() -> None:
    client = ExaEnrichmentClient(Settings())
    assert client.build_person_query("John", "Acme") == '"John" "Acme"'


@pytest.mark.anyio
async def test_exa_enrich_unconfigured() -> None:
    client = ExaEnrichmentClient(Settings())
    result = await client.enrich_person(EnrichmentRequest(name="Test"))
    assert result.success is False
    assert "not configured" in result.error


@pytest.mark.anyio
async def test_exa_enrich_with_mocked_api() -> None:
    settings = Settings(EXA_API_KEY="test-key-123")
    client = ExaEnrichmentClient(settings)

    mock_response = SimpleNamespace(results=MOCK_EXA_RESULTS)
    mock_exa = MagicMock()
    mock_exa.search_and_contents.return_value = mock_response
    client._client = mock_exa

    result = await client.enrich_person(
        EnrichmentRequest(name="Alice Smith", company="Google")
    )

    assert result.success is True
    assert len(result.hits) == 2
    assert result.hits[0].title == "Alice Smith - LinkedIn"
    assert result.hits[0].source == "exa"
    assert result.hits[0].score == 0.92
    assert "software engineer at Google" in result.hits[0].snippet
    assert result.hits[1].url == "https://x.com/alice"

    mock_exa.search_and_contents.assert_called_once()
    call_args = mock_exa.search_and_contents.call_args
    assert "Alice Smith" in call_args[0][0]
    assert "Google" in call_args[0][0]


@pytest.mark.anyio
async def test_exa_enrich_api_error() -> None:
    settings = Settings(EXA_API_KEY="test-key-123")
    client = ExaEnrichmentClient(settings)

    mock_exa = MagicMock()
    mock_exa.search_and_contents.side_effect = Exception("Network timeout")
    client._client = mock_exa

    result = await client.enrich_person(EnrichmentRequest(name="Test"))

    assert result.success is False
    assert "Network timeout" in result.error


@pytest.mark.anyio
async def test_exa_enrich_empty_results() -> None:
    settings = Settings(EXA_API_KEY="test-key-123")
    client = ExaEnrichmentClient(settings)

    mock_response = SimpleNamespace(results=[])
    mock_exa = MagicMock()
    mock_exa.search_and_contents.return_value = mock_response
    client._client = mock_exa

    result = await client.enrich_person(EnrichmentRequest(name="Nobody"))

    assert result.success is True
    assert len(result.hits) == 0


@pytest.mark.anyio
async def test_exa_enrich_with_additional_context() -> None:
    settings = Settings(EXA_API_KEY="test-key-123")
    client = ExaEnrichmentClient(settings)

    mock_response = SimpleNamespace(results=MOCK_EXA_RESULTS[:1])
    mock_exa = MagicMock()
    mock_exa.search_and_contents.return_value = mock_response
    client._client = mock_exa

    result = await client.enrich_person(
        EnrichmentRequest(name="Alice", additional_context="AI researcher Stanford")
    )

    assert result.success is True
    call_args = mock_exa.search_and_contents.call_args
    assert "AI researcher Stanford" in call_args[0][0]


@pytest.mark.anyio
async def test_exa_score_clamping() -> None:
    """Scores outside 0-1 should be clamped."""
    settings = Settings(EXA_API_KEY="test-key-123")
    client = ExaEnrichmentClient(settings)

    mock_result = SimpleNamespace(
        title="Test", url="https://example.com", text="Hi", highlights=[], score=1.5,
    )
    mock_response = SimpleNamespace(results=[mock_result])
    mock_exa = MagicMock()
    mock_exa.search_and_contents.return_value = mock_response
    client._client = mock_exa

    result = await client.enrich_person(EnrichmentRequest(name="Test"))
    assert result.hits[0].score == 1.0


# ── Synthesis Engine Tests ──


def test_synthesis_engine_not_configured() -> None:
    engine = GeminiSynthesisEngine(Settings())
    assert engine.configured is False


def test_synthesis_engine_configured() -> None:
    engine = GeminiSynthesisEngine(Settings(GEMINI_API_KEY="test-key"))
    assert engine.configured is True


@pytest.mark.anyio
async def test_synthesis_unconfigured() -> None:
    engine = GeminiSynthesisEngine(Settings())
    result = await engine.synthesize(SynthesisRequest(person_name="Alice"))
    assert result.success is False
    assert "not configured" in result.error


@pytest.mark.anyio
async def test_synthesis_with_mocked_gemini() -> None:
    settings = Settings(GEMINI_API_KEY="test-key-123")
    engine = GeminiSynthesisEngine(settings)

    mock_response = MagicMock()
    mock_response.text = MOCK_GEMINI_RESPONSE_JSON

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    engine._client = mock_client

    request = SynthesisRequest(
        person_name="Alice Smith",
        enrichment_snippets=["software engineer at Google", "Stanford PhD"],
        social_profiles=[
            SocialProfile(platform="twitter", url="https://x.com/alice", username="@alice"),
        ],
        raw_agent_data={"linkedin": "Alice Smith works at Google as a Software Engineer."},
    )

    result = await engine.synthesize(request)

    assert result.success is True
    assert result.person_name == "Alice Smith"
    assert result.occupation == "Software Engineer"
    assert result.organization == "Google"
    assert result.dossier is not None
    expected_summary = (
        "Alice Smith is a software engineer at Google,"
        " previously at Meta. Stanford PhD."
    )
    assert result.dossier.summary == expected_summary
    assert len(result.dossier.work_history) == 2
    assert result.dossier.work_history[0].role == "Software Engineer"
    assert result.dossier.work_history[0].company == "Google"
    assert len(result.dossier.education) == 1
    assert result.dossier.education[0].school == "Stanford University"
    assert result.dossier.social_profiles.twitter == "@alice"
    assert result.dossier.social_profiles.linkedin == "linkedin.com/in/alicesmith"
    assert len(result.dossier.conversation_hooks) == 2
    assert result.dossier.risk_flags == []

    mock_client.models.generate_content.assert_called_once()


@pytest.mark.anyio
async def test_synthesis_gemini_empty_response() -> None:
    settings = Settings(GEMINI_API_KEY="test-key-123")
    engine = GeminiSynthesisEngine(settings)

    mock_response = MagicMock()
    mock_response.text = ""

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Test"))

    assert result.success is False
    assert "empty response" in result.error


@pytest.mark.anyio
async def test_synthesis_gemini_invalid_json() -> None:
    settings = Settings(GEMINI_API_KEY="test-key-123")
    engine = GeminiSynthesisEngine(settings)

    mock_response = MagicMock()
    mock_response.text = "This is not JSON at all"

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Test"))

    assert result.success is False
    assert "not valid JSON" in result.error


@pytest.mark.anyio
async def test_synthesis_gemini_markdown_fenced_json() -> None:
    """Gemini sometimes wraps JSON in markdown code fences."""
    settings = Settings(GEMINI_API_KEY="test-key-123")
    engine = GeminiSynthesisEngine(settings)

    fenced = f"```json\n{MOCK_GEMINI_RESPONSE_JSON}\n```"
    mock_response = MagicMock()
    mock_response.text = fenced

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Alice Smith"))

    assert result.success is True
    assert result.dossier is not None
    assert result.dossier.title == "Software Engineer"


@pytest.mark.anyio
async def test_synthesis_gemini_api_error() -> None:
    settings = Settings(GEMINI_API_KEY="test-key-123")
    engine = GeminiSynthesisEngine(settings)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("API rate limit exceeded")
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Test"))

    assert result.success is False
    assert "rate limit" in result.error


@pytest.mark.anyio
async def test_synthesis_partial_data() -> None:
    """Engine should handle partial/minimal data gracefully."""
    settings = Settings(GEMINI_API_KEY="test-key-123")
    engine = GeminiSynthesisEngine(settings)

    minimal_json = json.dumps({
        "summary": "Unknown person",
        "title": None,
        "company": None,
        "work_history": [],
        "education": [],
        "social_profiles": {},
        "notable_activity": [],
        "conversation_hooks": [],
        "risk_flags": [],
    })

    mock_response = MagicMock()
    mock_response.text = minimal_json

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    engine._client = mock_client

    result = await engine.synthesize(SynthesisRequest(person_name="Unknown Person"))

    assert result.success is True
    assert result.dossier is not None
    assert result.dossier.summary == "Unknown person"
    assert result.dossier.work_history == []
    assert result.dossier.education == []
    assert result.dossier.conversation_hooks == []


def test_synthesis_build_raw_data_block_empty() -> None:
    engine = GeminiSynthesisEngine(Settings())
    request = SynthesisRequest(person_name="Empty")
    block = engine._build_raw_data_block(request)
    assert "No data available" in block


def test_synthesis_build_raw_data_block_full() -> None:
    engine = GeminiSynthesisEngine(Settings())
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


def test_synthesis_parse_gemini_response() -> None:
    engine = GeminiSynthesisEngine(Settings())
    dossier = engine._parse_gemini_response(MOCK_GEMINI_RESPONSE_JSON, "Alice")
    assert dossier.title == "Software Engineer"
    assert dossier.company == "Google"
    assert len(dossier.work_history) == 2
    assert len(dossier.education) == 1


def test_dossier_to_frontend_dict_matches_expected_shape() -> None:
    engine = GeminiSynthesisEngine(Settings())
    dossier = engine._parse_gemini_response(MOCK_GEMINI_RESPONSE_JSON, "Alice")
    d = dossier.to_frontend_dict()

    assert "summary" in d
    assert "title" in d
    assert "company" in d
    assert "workHistory" in d
    assert "education" in d
    assert "socialProfiles" in d
    assert "notableActivity" in d
    assert "conversationHooks" in d
    assert "riskFlags" in d

    assert isinstance(d["workHistory"], list)
    assert d["workHistory"][0]["role"] == "Software Engineer"
    assert d["education"][0]["school"] == "Stanford University"
    assert d["socialProfiles"]["twitter"] == "@alice"
