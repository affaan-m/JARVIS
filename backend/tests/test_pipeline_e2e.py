"""End-to-end integration test for the stitched pipeline.

Verifies: capture → detect → embed → Exa enrichment + browser research (parallel)
          → merge → Gemini synthesis → person record updated with dossier.

All external services (Exa, browser agents, Gemini) are mocked.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from agents.models import AgentResult, AgentStatus, OrchestratorResult, SocialProfile
from db.memory_gateway import InMemoryDatabaseGateway
from enrichment.models import EnrichmentHit, EnrichmentResult
from identification.embedder import ArcFaceEmbedder
from identification.models import (
    BoundingBox,
    DetectedFace,
    FaceDetectionRequest,
    FaceDetectionResult,
)
from pipeline import CapturePipeline
from synthesis.models import DossierReport, SocialProfiles, SynthesisResult

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_face(x: float = 0.1, y: float = 0.2, conf: float = 0.95) -> DetectedFace:
    return DetectedFace(
        bbox=BoundingBox(x=x, y=y, width=0.3, height=0.4),
        confidence=conf,
    )


class FakeDetector:
    def __init__(self, faces: list[DetectedFace] | None = None) -> None:
        self._faces = faces or []

    @property
    def configured(self) -> bool:
        return True

    async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
        return FaceDetectionResult(
            faces=self._faces,
            frame_width=100,
            frame_height=100,
            success=True,
        )


def _mock_exa_client(hits: list[EnrichmentHit] | None = None) -> MagicMock:
    client = MagicMock()
    result = EnrichmentResult(
        query='"Test Person"',
        hits=hits or [
            EnrichmentHit(
                title="Test Person - LinkedIn",
                url="https://linkedin.com/in/testperson",
                snippet="Software engineer at Acme Corp",
                score=0.9,
            ),
        ],
    )
    client.enrich_person = AsyncMock(return_value=result)
    return client


def _mock_orchestrator(
    profiles: list[SocialProfile] | None = None,
    snippets: list[str] | None = None,
) -> MagicMock:
    profiles = profiles or [
        SocialProfile(
            platform="twitter",
            url="https://x.com/testperson",
            username="testperson",
            bio="Building things",
        ),
    ]
    snippets = snippets or ["Active on Twitter, 5K followers"]
    agent_result = AgentResult(
        agent_name="twitter",
        status=AgentStatus.SUCCESS,
        profiles=profiles,
        snippets=snippets,
        completed_at=datetime.now(UTC),
    )
    orch_result = OrchestratorResult(
        person_name="Test Person",
        agent_results={"twitter": agent_result},
        all_profiles=profiles,
        all_snippets=snippets,
        total_duration_seconds=1.5,
        success=True,
    )
    orch = MagicMock()
    orch.research_person = AsyncMock(return_value=orch_result)
    return orch


def _mock_synthesis_engine(
    summary: str = "Test Person is a software engineer at Acme Corp.",
    dossier: DossierReport | None = None,
) -> MagicMock:
    if dossier is None:
        dossier = DossierReport(
            summary=summary,
            title="Software Engineer",
            company="Acme Corp",
            social_profiles=SocialProfiles(twitter="@testperson"),
            conversation_hooks=["Ask about Acme Corp"],
        )
    result = SynthesisResult(
        person_name="Test Person",
        summary=summary,
        occupation="Software Engineer",
        organization="Acme Corp",
        dossier=dossier,
        confidence_score=0.8,
    )
    engine = MagicMock()
    engine.synthesize = AsyncMock(return_value=result)
    return engine


# ── Full Pipeline E2E ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_pipeline_e2e_with_enrichment() -> None:
    """Complete flow: capture → detect → enrich+research → synthesize → store dossier."""
    face = _make_face()
    db = InMemoryDatabaseGateway()

    pipeline = CapturePipeline(
        detector=FakeDetector(faces=[face]),
        embedder=ArcFaceEmbedder(),
        db=db,
        exa_client=_mock_exa_client(),
        orchestrator=_mock_orchestrator(),
        synthesis_engine=_mock_synthesis_engine(),
    )

    result = await pipeline.process(
        capture_id="cap_e2e_001",
        data=_make_jpeg(),
        content_type="image/jpeg",
        person_name="Test Person",
    )

    assert result.success is True
    assert result.faces_detected == 1
    assert len(result.persons_created) == 1
    assert result.persons_enriched == 1

    # Verify person record has dossier
    person = await db.get_person(result.persons_created[0])
    assert person is not None
    assert person["status"] == "enriched"
    assert person["summary"] == "Test Person is a software engineer at Acme Corp."
    assert person["occupation"] == "Software Engineer"
    assert person["organization"] == "Acme Corp"
    assert "dossier" in person
    assert person["dossier"]["title"] == "Software Engineer"


@pytest.mark.asyncio
async def test_pipeline_enrichment_without_person_name_skips() -> None:
    """When no person_name is given, enrichment is skipped."""
    face = _make_face()
    db = InMemoryDatabaseGateway()
    exa = _mock_exa_client()

    pipeline = CapturePipeline(
        detector=FakeDetector(faces=[face]),
        embedder=ArcFaceEmbedder(),
        db=db,
        exa_client=exa,
        orchestrator=_mock_orchestrator(),
        synthesis_engine=_mock_synthesis_engine(),
    )

    result = await pipeline.process(
        capture_id="cap_no_name",
        data=_make_jpeg(),
        content_type="image/jpeg",
        # No person_name → skip enrichment
    )

    assert result.success is True
    assert result.persons_enriched == 0
    exa.enrich_person.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_exa_failure_still_succeeds() -> None:
    """Exa failure doesn't crash the pipeline; synthesis still runs with browser data."""
    face = _make_face()
    db = InMemoryDatabaseGateway()

    failing_exa = MagicMock()
    failing_exa.enrich_person = AsyncMock(side_effect=RuntimeError("Exa down"))

    pipeline = CapturePipeline(
        detector=FakeDetector(faces=[face]),
        embedder=ArcFaceEmbedder(),
        db=db,
        exa_client=failing_exa,
        orchestrator=_mock_orchestrator(),
        synthesis_engine=_mock_synthesis_engine(),
    )

    result = await pipeline.process(
        capture_id="cap_exa_fail",
        data=_make_jpeg(),
        content_type="image/jpeg",
        person_name="Test Person",
    )

    assert result.success is True
    assert result.persons_enriched == 1

    person = await db.get_person(result.persons_created[0])
    assert person["status"] == "enriched"


@pytest.mark.asyncio
async def test_pipeline_browser_failure_still_succeeds() -> None:
    """Browser orchestrator failure doesn't crash; synthesis runs with Exa data."""
    face = _make_face()
    db = InMemoryDatabaseGateway()

    failing_orch = MagicMock()
    failing_orch.research_person = AsyncMock(side_effect=RuntimeError("Browser agents down"))

    pipeline = CapturePipeline(
        detector=FakeDetector(faces=[face]),
        embedder=ArcFaceEmbedder(),
        db=db,
        exa_client=_mock_exa_client(),
        orchestrator=failing_orch,
        synthesis_engine=_mock_synthesis_engine(),
    )

    result = await pipeline.process(
        capture_id="cap_browser_fail",
        data=_make_jpeg(),
        content_type="image/jpeg",
        person_name="Test Person",
    )

    assert result.success is True
    assert result.persons_enriched == 1


@pytest.mark.asyncio
async def test_pipeline_synthesis_failure_marks_person() -> None:
    """Synthesis failure updates person status but doesn't crash pipeline."""
    face = _make_face()
    db = InMemoryDatabaseGateway()

    failing_synthesis = MagicMock()
    failing_synthesis.synthesize = AsyncMock(
        return_value=SynthesisResult(
            person_name="Test Person",
            success=False,
            error="Gemini rate limited",
        )
    )

    pipeline = CapturePipeline(
        detector=FakeDetector(faces=[face]),
        embedder=ArcFaceEmbedder(),
        db=db,
        exa_client=_mock_exa_client(),
        orchestrator=_mock_orchestrator(),
        synthesis_engine=failing_synthesis,
    )

    result = await pipeline.process(
        capture_id="cap_synth_fail",
        data=_make_jpeg(),
        content_type="image/jpeg",
        person_name="Test Person",
    )

    assert result.success is True
    assert result.persons_enriched == 0

    person = await db.get_person(result.persons_created[0])
    assert person["status"] == "synthesis_failed"
    assert "rate limited" in person["synthesis_error"]


@pytest.mark.asyncio
async def test_pipeline_no_enrichment_deps_still_works() -> None:
    """Pipeline works without enrichment services (backward compatible)."""
    face = _make_face()
    db = InMemoryDatabaseGateway()

    pipeline = CapturePipeline(
        detector=FakeDetector(faces=[face]),
        embedder=ArcFaceEmbedder(),
        db=db,
        # No exa, orchestrator, or synthesis
    )

    result = await pipeline.process(
        capture_id="cap_minimal",
        data=_make_jpeg(),
        content_type="image/jpeg",
        person_name="Test Person",
    )

    assert result.success is True
    assert result.faces_detected == 1
    assert result.persons_enriched == 0


@pytest.mark.asyncio
async def test_pipeline_multiple_faces_all_enriched() -> None:
    """Multiple faces each get enriched independently."""
    faces = [_make_face(x=0.1, conf=0.95), _make_face(x=0.5, conf=0.90)]
    db = InMemoryDatabaseGateway()

    pipeline = CapturePipeline(
        detector=FakeDetector(faces=faces),
        embedder=ArcFaceEmbedder(),
        db=db,
        exa_client=_mock_exa_client(),
        orchestrator=_mock_orchestrator(),
        synthesis_engine=_mock_synthesis_engine(),
    )

    result = await pipeline.process(
        capture_id="cap_multi",
        data=_make_jpeg(),
        content_type="image/jpeg",
        person_name="Test Person",
    )

    assert result.success is True
    assert result.faces_detected == 2
    assert len(result.persons_created) == 2
    assert result.persons_enriched == 2


# ── Merge Logic Unit Tests ───────────────────────────────────────────────────


class TestMergeToSynthesisRequest:
    def test_merge_both_sources(self) -> None:
        exa = EnrichmentResult(
            query='"Alice"',
            hits=[
                EnrichmentHit(title="Alice - LI", url="https://linkedin.com/in/a", snippet="eng"),
            ],
        )
        browser = OrchestratorResult(
            person_name="Alice",
            agent_results={
                "twitter": AgentResult(
                    agent_name="twitter",
                    status=AgentStatus.SUCCESS,
                    snippets=["Tweeted about AI"],
                ),
            },
            all_profiles=[
                SocialProfile(platform="twitter", url="https://x.com/alice", username="alice"),
            ],
            all_snippets=["Tweeted about AI"],
            success=True,
        )

        req = CapturePipeline._merge_to_synthesis_request("Alice", exa, browser)

        assert req.person_name == "Alice"
        assert len(req.enrichment_snippets) == 2  # 1 exa + 1 browser snippet
        assert len(req.social_profiles) == 1
        assert req.social_profiles[0].platform == "twitter"
        assert "twitter" in req.raw_agent_data

    def test_merge_exa_only(self) -> None:
        exa = EnrichmentResult(
            query='"Bob"',
            hits=[
                EnrichmentHit(title="Bob", url="https://bob.com", snippet="CEO"),
            ],
        )

        req = CapturePipeline._merge_to_synthesis_request("Bob", exa, None)

        assert len(req.enrichment_snippets) == 1
        assert req.social_profiles == []
        assert req.raw_agent_data == {}

    def test_merge_browser_only(self) -> None:
        browser = OrchestratorResult(
            person_name="Carol",
            agent_results={},
            all_profiles=[
                SocialProfile(platform="linkedin", url="https://linkedin.com/in/carol"),
            ],
            all_snippets=["Found on LinkedIn"],
            success=True,
        )

        req = CapturePipeline._merge_to_synthesis_request("Carol", None, browser)

        assert len(req.enrichment_snippets) == 1
        assert len(req.social_profiles) == 1

    def test_merge_both_none(self) -> None:
        req = CapturePipeline._merge_to_synthesis_request("Nobody", None, None)

        assert req.person_name == "Nobody"
        assert req.enrichment_snippets == []
        assert req.social_profiles == []
        assert req.raw_agent_data == {}

    def test_merge_failed_results_ignored(self) -> None:
        exa = EnrichmentResult(query='"X"', success=False, error="down")
        browser = OrchestratorResult(
            person_name="X", success=False, error="All agents failed",
        )

        req = CapturePipeline._merge_to_synthesis_request("X", exa, browser)

        assert req.enrichment_snippets == []
        assert req.social_profiles == []
