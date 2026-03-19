"""Tests for synthesis.connections — connection detection algorithm."""

from __future__ import annotations

from synthesis.connections import (
    _check_classmate,
    _check_co_mentioned,
    _check_colleague,
    _check_same_location,
    _extract_location_signals,
    detect_connections,
)
from synthesis.models import DossierReport, EducationEntry, WorkHistoryEntry


def _make_dossier(
    *,
    summary: str = "",
    company: str | None = None,
    work_history: list[dict] | None = None,
    education: list[dict] | None = None,
    notable_activity: list[str] | None = None,
    conversation_hooks: list[str] | None = None,
) -> DossierReport:
    return DossierReport(
        summary=summary,
        company=company,
        work_history=[WorkHistoryEntry(**w) for w in (work_history or [])],
        education=[EducationEntry(**e) for e in (education or [])],
        notable_activity=notable_activity or [],
        conversation_hooks=conversation_hooks or [],
    )


class TestCheckColleague:
    def test_shared_current_company(self):
        a = _make_dossier(company="Acme Corp")
        b = _make_dossier(company="Acme Corp")
        result = _check_colleague("p1", a, "p2", b)
        assert result is not None
        assert result.relationship_type == "colleague"
        assert result.confidence == 0.85
        assert "acme corp" in result.description.lower()

    def test_shared_work_history_not_current(self):
        a = _make_dossier(
            company="NewCo",
            work_history=[{"role": "Eng", "company": "OldCo"}],
        )
        b = _make_dossier(
            company="OtherCo",
            work_history=[{"role": "PM", "company": "OldCo"}],
        )
        result = _check_colleague("p1", a, "p2", b)
        assert result is not None
        assert result.confidence == 0.6
        assert "oldco" in result.description.lower()

    def test_no_shared_company(self):
        a = _make_dossier(company="Alpha")
        b = _make_dossier(company="Beta")
        result = _check_colleague("p1", a, "p2", b)
        assert result is None

    def test_case_insensitive(self):
        a = _make_dossier(company="GOOGLE")
        b = _make_dossier(company="google")
        result = _check_colleague("p1", a, "p2", b)
        assert result is not None


class TestCheckClassmate:
    def test_shared_school(self):
        a = _make_dossier(education=[{"school": "MIT", "degree": "BS CS"}])
        b = _make_dossier(education=[{"school": "MIT", "degree": "MS EE"}])
        result = _check_classmate("p1", a, "p2", b)
        assert result is not None
        assert result.relationship_type == "classmate"
        assert result.confidence == 0.7
        assert "mit" in result.description.lower()

    def test_no_shared_school(self):
        a = _make_dossier(education=[{"school": "MIT"}])
        b = _make_dossier(education=[{"school": "Stanford"}])
        result = _check_classmate("p1", a, "p2", b)
        assert result is None

    def test_empty_education(self):
        a = _make_dossier()
        b = _make_dossier(education=[{"school": "MIT"}])
        result = _check_classmate("p1", a, "p2", b)
        assert result is None


class TestCheckSameLocation:
    def test_shared_location_in_summary(self):
        a = _make_dossier(summary="Based in San Francisco, working on AI")
        b = _make_dossier(summary="San Francisco-based engineer at Stripe")
        result = _check_same_location("p1", a, "p2", b)
        assert result is not None
        assert result.relationship_type == "same_location"
        assert result.confidence == 0.4

    def test_no_location_overlap(self):
        a = _make_dossier(summary="Lives in London")
        b = _make_dossier(summary="Based in Tokyo")
        result = _check_same_location("p1", a, "p2", b)
        assert result is None

    def test_empty_summaries(self):
        a = _make_dossier()
        b = _make_dossier()
        result = _check_same_location("p1", a, "p2", b)
        assert result is None


class TestExtractLocationSignals:
    def test_finds_known_cities(self):
        signals = _extract_location_signals("Based in San Francisco and New York")
        assert "san francisco" in signals
        assert "new york" in signals

    def test_empty_text(self):
        assert _extract_location_signals("") == set()

    def test_sf_abbreviation(self):
        assert "sf" in _extract_location_signals("Working in SF")


class TestCheckCoMentioned:
    def test_cross_reference_in_activity(self):
        a = _make_dossier(
            notable_activity=["Spoke at Google I/O 2025"],
            work_history=[{"role": "Eng", "company": "Meta"}],
        )
        b = _make_dossier(
            notable_activity=["Works closely with Meta team"],
            work_history=[{"role": "Eng", "company": "Google"}],
        )
        result = _check_co_mentioned("p1", a, "p2", b)
        assert result is not None
        assert result.relationship_type == "co_mentioned"

    def test_no_cross_reference(self):
        a = _make_dossier(
            notable_activity=["Won hackathon"],
            work_history=[{"role": "Eng", "company": "Startup"}],
        )
        b = _make_dossier(
            notable_activity=["Published paper"],
            work_history=[{"role": "Prof", "company": "University"}],
        )
        result = _check_co_mentioned("p1", a, "p2", b)
        assert result is None


class TestDetectConnections:
    def test_full_detection_with_multiple_signals(self):
        new_dossier = _make_dossier(
            company="Anthropic",
            education=[{"school": "Stanford"}],
            summary="AI researcher in San Francisco",
            work_history=[{"role": "Research Scientist", "company": "Anthropic"}],
        )

        existing = [
            {
                "person_id": "existing_1",
                "dossier": _make_dossier(
                    company="Anthropic",
                    education=[{"school": "MIT"}],
                    summary="ML engineer in San Francisco",
                    work_history=[{"role": "ML Eng", "company": "Anthropic"}],
                ),
            },
            {
                "person_id": "existing_2",
                "dossier": _make_dossier(
                    company="Google",
                    education=[{"school": "Stanford"}],
                    summary="Based in New York",
                    work_history=[{"role": "SWE", "company": "Google"}],
                ),
            },
        ]

        results = detect_connections("new_person", new_dossier, existing)

        # Should find: colleague with existing_1 (Anthropic), same_location with existing_1 (SF)
        # classmate with existing_2 (Stanford)
        types = {(r.person_b_id, r.relationship_type) for r in results}
        assert ("existing_1", "colleague") in types
        assert ("existing_1", "same_location") in types
        assert ("existing_2", "classmate") in types

    def test_skips_self(self):
        dossier = _make_dossier(company="Acme")
        existing = [{"person_id": "self_id", "dossier": dossier}]
        results = detect_connections("self_id", dossier, existing)
        assert len(results) == 0

    def test_skips_persons_without_dossier(self):
        dossier = _make_dossier(company="Acme")
        existing = [{"person_id": "no_dossier", "dossier": None}]
        results = detect_connections("new", dossier, existing)
        assert len(results) == 0

    def test_no_connections_for_unrelated(self):
        a = _make_dossier(company="Alpha", summary="Living in London")
        b_raw = {
            "person_id": "other",
            "dossier": _make_dossier(company="Beta", summary="Based in Tokyo"),
        }
        results = detect_connections("new", a, [b_raw])
        assert len(results) == 0

    def test_handles_raw_dict_dossier(self):
        new_dossier = _make_dossier(company="Acme")
        existing = [
            {
                "person_id": "dict_person",
                "dossier": {
                    "summary": "",
                    "company": "Acme",
                    "work_history": [],
                    "education": [],
                    "notable_activity": [],
                    "conversation_hooks": [],
                    "risk_flags": [],
                },
            },
        ]
        results = detect_connections("new", new_dossier, existing)
        colleague_results = [r for r in results if r.relationship_type == "colleague"]
        assert len(colleague_results) == 1
