"""Fixture-based tests for service adapter contracts.

Validates that each adapter:
- Conforms to its Protocol interface
- Handles unconfigured state gracefully
- Produces correctly shaped request/response payloads
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from config import Settings
from db.convex_client import ConvexGateway
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentHit, EnrichmentRequest, EnrichmentResult
from env_check import check_all_services, check_service
from identification.models import (
    BoundingBox,
    DetectedFace,
    FaceDetectionRequest,
    FaceDetectionResult,
    FaceSearchMatch,
    FaceSearchRequest,
    FaceSearchResult,
)
from observability.laminar import LaminarTracingClient
from synthesis.models import (
    ConnectionEdge,
    SocialProfile,
    SynthesisRequest,
    SynthesisResult,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def unconfigured_settings() -> Settings:
    """Settings with no external services configured."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        CONVEX_URL=None,
        EXA_API_KEY=None,
        LAMINAR_API_KEY=None,
        GEMINI_API_KEY=None,
    )


@pytest.fixture()
def configured_settings() -> Settings:
    """Settings with all services configured (fake keys)."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        CONVEX_URL="https://fake.convex.cloud",
        MONGODB_URI="mongodb://localhost:27017/test",
        EXA_API_KEY="exa_test_key",
        BROWSER_USE_API_KEY="bu_test_key",
        OPENAI_API_KEY="sk-test",
        GEMINI_API_KEY="gem_test_key",
        LAMINAR_API_KEY="lam_test_key",
        TELEGRAM_BOT_TOKEN="123:ABC",
        PIMEYES_ACCOUNT_POOL='[{"email":"test@test.com"}]',
    )


@pytest.fixture()
def convex_unconfigured(unconfigured_settings: Settings) -> ConvexGateway:
    return ConvexGateway(unconfigured_settings)


@pytest.fixture()
def convex_configured(configured_settings: Settings) -> ConvexGateway:
    return ConvexGateway(configured_settings)


@pytest.fixture()
def exa_unconfigured(unconfigured_settings: Settings) -> ExaEnrichmentClient:
    return ExaEnrichmentClient(unconfigured_settings)


@pytest.fixture()
def exa_configured(configured_settings: Settings) -> ExaEnrichmentClient:
    return ExaEnrichmentClient(configured_settings)


@pytest.fixture()
def laminar_unconfigured(unconfigured_settings: Settings) -> LaminarTracingClient:
    return LaminarTracingClient(unconfigured_settings)


@pytest.fixture()
def laminar_configured(configured_settings: Settings) -> LaminarTracingClient:
    return LaminarTracingClient(configured_settings)


# ── ConvexGateway Tests ──────────────────────────────────────────────────────


class TestConvexGateway:
    def test_unconfigured_reports_false(self, convex_unconfigured: ConvexGateway) -> None:
        assert convex_unconfigured.configured is False

    def test_configured_reports_true(self, convex_configured: ConvexGateway) -> None:
        assert convex_configured.configured is True

    def test_store_person_raises_when_unconfigured(
        self, convex_unconfigured: ConvexGateway
    ) -> None:
        with pytest.raises(RuntimeError, match="CONVEX_URL"):
            asyncio.run(convex_unconfigured.store_person("p_1", {"name": "Test"}))

    def test_store_person_returns_id(self, convex_configured: ConvexGateway) -> None:
        convex_configured._mutation = AsyncMock(return_value="p_1")
        result = asyncio.run(convex_configured.store_person("p_1", {"name": "Test"}))
        assert result == "p_1"

    def test_get_person_returns_none_placeholder(
        self, convex_configured: ConvexGateway
    ) -> None:
        convex_configured._query = AsyncMock(return_value=None)
        result = asyncio.run(convex_configured.get_person("p_1"))
        assert result is None

    def test_store_capture_raises_when_unconfigured(
        self, convex_unconfigured: ConvexGateway
    ) -> None:
        with pytest.raises(RuntimeError, match="CONVEX_URL"):
            asyncio.run(convex_unconfigured.store_capture("cap_1", {"file": "test.jpg"}))

    def test_store_capture_returns_id(self, convex_configured: ConvexGateway) -> None:
        convex_configured._mutation = AsyncMock(return_value="cap_1")
        result = asyncio.run(convex_configured.store_capture("cap_1", {"file": "test.jpg"}))
        assert result == "cap_1"


# ── ExaEnrichmentClient Tests ───────────────────────────────────────────────


class TestExaEnrichmentClient:
    def test_unconfigured_reports_false(self, exa_unconfigured: ExaEnrichmentClient) -> None:
        assert exa_unconfigured.configured is False

    def test_configured_reports_true(self, exa_configured: ExaEnrichmentClient) -> None:
        assert exa_configured.configured is True

    def test_build_person_query_name_only(self, exa_configured: ExaEnrichmentClient) -> None:
        q = exa_configured.build_person_query("John Doe")
        assert q == '"John Doe"'

    def test_build_person_query_with_company(self, exa_configured: ExaEnrichmentClient) -> None:
        q = exa_configured.build_person_query("John Doe", "Acme")
        assert q == '"John Doe" "Acme"'

    def test_enrich_returns_error_when_unconfigured(
        self, exa_unconfigured: ExaEnrichmentClient
    ) -> None:
        req = EnrichmentRequest(name="Test Person")
        result = asyncio.run(exa_unconfigured.enrich_person(req))
        assert result.success is False
        assert result.error is not None
        assert "EXA_API_KEY" in result.error

    def test_enrich_returns_hits_when_configured(
        self, exa_configured: ExaEnrichmentClient
    ) -> None:
        mock_result = SimpleNamespace(
            title="Test Person - LinkedIn",
            url="https://linkedin.com/in/testperson",
            text="Test Person is an engineer at TestCorp.",
            highlights=["engineer at TestCorp"],
            score=0.9,
        )
        mock_response = SimpleNamespace(results=[mock_result])
        mock_exa = MagicMock()
        mock_exa.search_and_contents.return_value = mock_response
        exa_configured._client = mock_exa

        req = EnrichmentRequest(name="Test Person", company="TestCorp")
        result = asyncio.run(exa_configured.enrich_person(req))
        assert result.success is True
        assert len(result.hits) > 0
        assert result.hits[0].source == "exa"


# ── LaminarTracingClient Tests ──────────────────────────────────────────────


class TestLaminarTracingClient:
    def test_unconfigured_reports_false(self, laminar_unconfigured: LaminarTracingClient) -> None:
        assert laminar_unconfigured.configured is False

    def test_configured_reports_true(self, laminar_configured: LaminarTracingClient) -> None:
        assert laminar_configured.configured is True

    def test_trace_event_does_not_raise_when_unconfigured(
        self, laminar_unconfigured: LaminarTracingClient
    ) -> None:
        laminar_unconfigured.trace_event("test_event", {"key": "value"})

    def test_trace_span_lifecycle(self, laminar_configured: LaminarTracingClient) -> None:
        span_id = laminar_configured.trace_span_start("test_span", {"detail": "abc"})
        assert span_id.startswith("span_")
        laminar_configured.trace_span_end(span_id, {"result": "ok"})


# ── Pydantic Model Shape Tests ──────────────────────────────────────────────


class TestEnrichmentModels:
    def test_enrichment_request_minimal(self) -> None:
        req = EnrichmentRequest(name="Jane Doe")
        assert req.name == "Jane Doe"
        assert req.company is None

    def test_enrichment_request_full(self) -> None:
        req = EnrichmentRequest(name="Jane Doe", company="BigCo", additional_context="CEO")
        assert req.company == "BigCo"

    def test_enrichment_hit_defaults(self) -> None:
        hit = EnrichmentHit(title="Test", url="https://example.com")
        assert hit.score == 0.0
        assert hit.source == "exa"

    def test_enrichment_result_empty(self) -> None:
        result = EnrichmentResult(query="test")
        assert result.hits == []
        assert result.success is True


class TestIdentificationModels:
    def test_bounding_box_valid(self) -> None:
        bb = BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4)
        assert bb.x == 0.1

    def test_bounding_box_rejects_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            BoundingBox(x=1.5, y=0.0, width=0.1, height=0.1)

    def test_detected_face_shape(self) -> None:
        face = DetectedFace(
            bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2),
            confidence=0.95,
            embedding=[0.1, 0.2, 0.3],
        )
        assert face.confidence == 0.95
        assert len(face.embedding) == 3

    def test_face_detection_request(self) -> None:
        req = FaceDetectionRequest(image_data=b"\x89PNG", max_faces=5, min_confidence=0.7)
        assert req.max_faces == 5

    def test_face_detection_result_empty(self) -> None:
        result = FaceDetectionResult()
        assert result.faces == []
        assert result.success is True

    def test_face_search_request_defaults(self) -> None:
        req = FaceSearchRequest(embedding=[0.1, 0.2])
        assert req.search_engines == ["pimeyes"]

    def test_face_search_match_shape(self) -> None:
        match = FaceSearchMatch(
            url="https://linkedin.com/in/test",
            similarity=0.92,
            source="pimeyes",
            person_name="John Doe",
        )
        assert match.similarity == 0.92

    def test_face_search_result_with_matches(self) -> None:
        result = FaceSearchResult(
            matches=[
                FaceSearchMatch(url="https://example.com", similarity=0.8, source="pimeyes")
            ]
        )
        assert len(result.matches) == 1


class TestSynthesisModels:
    def test_social_profile_shape(self) -> None:
        profile = SocialProfile(platform="twitter", url="https://x.com/test", username="test")
        assert profile.platform == "twitter"

    def test_connection_edge_defaults(self) -> None:
        edge = ConnectionEdge(person_name="Jane", relationship="colleague")
        assert edge.confidence == 0.5

    def test_synthesis_request_minimal(self) -> None:
        req = SynthesisRequest(person_name="Test Person")
        assert req.face_search_urls == []
        assert req.enrichment_snippets == []

    def test_synthesis_request_full(self) -> None:
        req = SynthesisRequest(
            person_name="Test Person",
            face_search_urls=["https://example.com/face"],
            enrichment_snippets=["CEO of TestCorp"],
            social_profiles=[
                SocialProfile(platform="linkedin", url="https://linkedin.com/in/test")
            ],
            raw_agent_data={"linkedin": "scraped data"},
        )
        assert len(req.social_profiles) == 1

    def test_synthesis_result_defaults(self) -> None:
        result = SynthesisResult(person_name="Test")
        assert result.summary == ""
        assert result.success is True
        assert result.connections == []

    def test_synthesis_result_full(self) -> None:
        result = SynthesisResult(
            person_name="Test Person",
            summary="Test summary",
            occupation="Engineer",
            organization="TestCorp",
            location="SF, CA",
            social_profiles=[SocialProfile(platform="twitter", url="https://x.com/test")],
            connections=[
                ConnectionEdge(person_name="Bob", relationship="manager", confidence=0.9)
            ],
            key_facts=["Fact 1", "Fact 2"],
            confidence_score=0.85,
        )
        assert result.confidence_score == 0.85
        assert len(result.key_facts) == 2


# ── Environment Validation Tests ─────────────────────────────────────────────


class TestEnvCheck:
    def test_check_service_unconfigured(self, unconfigured_settings: Settings) -> None:
        result = check_service("exa", unconfigured_settings)
        assert result.ready is False
        assert len(result.missing_vars) > 0

    def test_check_service_configured(self, configured_settings: Settings) -> None:
        result = check_service("exa", configured_settings)
        assert result.ready is True
        assert result.missing_vars == []

    def test_check_all_services_returns_all(self, configured_settings: Settings) -> None:
        results = check_all_services(configured_settings)
        names = {r.name for r in results}
        assert "convex" in names
        assert "exa" in names
        assert "laminar" in names

    def test_check_all_services_unconfigured_has_failures(
        self, unconfigured_settings: Settings
    ) -> None:
        results = check_all_services(unconfigured_settings)
        assert any(not r.ready for r in results)

    def test_check_unknown_service(self, configured_settings: Settings) -> None:
        result = check_service("nonexistent", configured_settings)
        assert result.ready is True
        assert result.missing_vars == []
