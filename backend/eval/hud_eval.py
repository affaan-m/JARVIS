# RESEARCH: hud-python 0.5.29 (HUD SDK), httpx (bundled), pydantic (project dep)
# DECISION: Custom eval harness using HUD Environment + scenarios for pipeline quality
# ALT: Pure pytest scoring — simpler but no HUD platform integration or A/B testing
"""
SPECTER Pipeline Eval Harness
=============================

Evaluates dossier output quality across three axes:
  1. Completeness — does the dossier have work history, education, social profiles?
  2. Accuracy     — do URLs actually resolve?
  3. Synthesis    — is the summary coherent and non-empty?

Usage:
    python -m eval.hud_eval                      # run all test subjects
    python -m eval.hud_eval --name "Sam Altman"  # run one subject
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from loguru import logger

# Add parent to path so we can import project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings
from synthesis.models import DossierReport


# ---------------------------------------------------------------------------
# Eval scoring functions (pure, no side effects)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvalScores:
    """Scores for a single dossier evaluation."""

    subject_name: str
    completeness: float = 0.0
    accuracy: float = 0.0
    synthesis: float = 0.0
    overall: float = 0.0
    details: dict[str, object] = field(default_factory=dict)
    elapsed_s: float = 0.0


def score_completeness(dossier: DossierReport) -> tuple[float, dict[str, bool]]:
    """Score how complete a dossier is (0.0 - 1.0).

    Checks presence of: summary, title, company, work_history,
    education, social_profiles (at least 1 link), notable_activity,
    conversation_hooks.
    """
    checks = {
        "has_summary": bool(dossier.summary and len(dossier.summary) > 20),
        "has_title": bool(dossier.title),
        "has_company": bool(dossier.company),
        "has_work_history": len(dossier.work_history) > 0,
        "has_education": len(dossier.education) > 0,
        "has_social_profiles": _has_any_social(dossier),
        "has_notable_activity": len(dossier.notable_activity) > 0,
        "has_conversation_hooks": len(dossier.conversation_hooks) > 0,
    }
    score = sum(checks.values()) / len(checks)
    return score, checks


def _has_any_social(dossier: DossierReport) -> bool:
    sp = dossier.social_profiles
    return any([sp.linkedin, sp.twitter, sp.instagram, sp.github, sp.website])


async def score_accuracy(dossier: DossierReport, timeout: float = 10.0) -> tuple[float, dict[str, bool]]:
    """Score URL accuracy by checking if social profile URLs resolve (2xx/3xx).

    Returns (score, {url: resolved_bool}).
    """
    urls: dict[str, str] = {}
    sp = dossier.social_profiles
    if sp.linkedin:
        urls["linkedin"] = _normalize_url(sp.linkedin)
    if sp.twitter:
        urls["twitter"] = _normalize_url(sp.twitter)
    if sp.instagram:
        urls["instagram"] = _normalize_url(sp.instagram)
    if sp.github:
        urls["github"] = _normalize_url(sp.github)
    if sp.website:
        urls["website"] = _normalize_url(sp.website)

    if not urls:
        return 0.0, {"no_urls": False}

    results: dict[str, bool] = {}
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": "SPECTER-Eval/1.0"},
    ) as client:
        for label, url in urls.items():
            try:
                resp = await client.head(url)
                results[f"{label}:{url}"] = resp.status_code < 400
            except Exception:
                results[f"{label}:{url}"] = False

    if not results:
        return 0.0, results

    score = sum(results.values()) / len(results)
    return score, results


def _normalize_url(raw: str) -> str:
    """Ensure a URL has a scheme."""
    raw = raw.strip()
    if raw.startswith("@"):
        return f"https://x.com/{raw.lstrip('@')}"
    if not raw.startswith("http"):
        return f"https://{raw}"
    return raw


def score_synthesis(dossier: DossierReport) -> tuple[float, dict[str, object]]:
    """Score synthesis quality: summary length, specificity, risk flags sanity.

    This is a heuristic — a real eval would use LLM-as-judge.
    """
    details: dict[str, object] = {}
    points = 0.0
    max_points = 5.0

    # Summary quality (0-2 points)
    summary_len = len(dossier.summary)
    if summary_len > 100:
        points += 2.0
        details["summary_quality"] = "good"
    elif summary_len > 40:
        points += 1.0
        details["summary_quality"] = "adequate"
    else:
        details["summary_quality"] = "too_short"
    details["summary_length"] = summary_len

    # Conversation hooks specificity (0-1 points)
    hooks_count = len(dossier.conversation_hooks)
    if hooks_count >= 2:
        points += 1.0
        details["hooks_quality"] = "good"
    elif hooks_count == 1:
        points += 0.5
        details["hooks_quality"] = "minimal"
    else:
        details["hooks_quality"] = "missing"

    # Work history depth (0-1 points)
    wh_count = len(dossier.work_history)
    if wh_count >= 2:
        points += 1.0
        details["work_history_depth"] = "good"
    elif wh_count == 1:
        points += 0.5
        details["work_history_depth"] = "minimal"
    else:
        details["work_history_depth"] = "missing"

    # Risk flags sanity — not empty for public figures, not excessive (0-1 point)
    rf_count = len(dossier.risk_flags)
    if rf_count <= 5:
        points += 1.0
        details["risk_flags_sanity"] = "ok"
    else:
        points += 0.5
        details["risk_flags_sanity"] = "excessive"
    details["risk_flags_count"] = rf_count

    return points / max_points, details


# ---------------------------------------------------------------------------
# Pipeline runner — calls the real synthesis engine
# ---------------------------------------------------------------------------

async def run_pipeline_for_subject(person_name: str) -> DossierReport | None:
    """Run the enrichment + synthesis pipeline for a person and return the dossier.

    Uses Exa enrichment (fast) + Anthropic synthesis to produce a dossier.
    Skips face detection / browser agents since eval subjects are name-only.
    """
    settings = get_settings()

    # Exa enrichment
    exa_result = None
    if settings.exa_api_key:
        from enrichment.exa_client import ExaEnrichmentClient
        from enrichment.models import EnrichmentRequest

        exa_client = ExaEnrichmentClient(settings)
        exa_result = await exa_client.enrich_person(
            EnrichmentRequest(name=person_name),
        )
        if not exa_result.success:
            logger.warning("Exa enrichment failed for {}: {}", person_name, exa_result.error)
            exa_result = None

    # Build synthesis request from Exa results
    from pipeline import CapturePipeline
    synthesis_request = CapturePipeline._merge_to_synthesis_request(
        person_name, exa_result, None,
    )

    # Try Anthropic synthesis (primary for eval — avoids Gemini 429s)
    from synthesis.anthropic_engine import AnthropicSynthesisEngine
    engine = AnthropicSynthesisEngine(settings)

    if not engine.configured:
        # Fall back to Gemini
        from synthesis.engine import GeminiSynthesisEngine
        gemini = GeminiSynthesisEngine(settings)
        result = await gemini.synthesize(synthesis_request)
    else:
        result = await engine.synthesize(synthesis_request)

    if not result.success:
        logger.error("Synthesis failed for {}: {}", person_name, result.error)
        return None

    return result.dossier


# ---------------------------------------------------------------------------
# HUD Environment (eval scenarios)
# ---------------------------------------------------------------------------

try:
    from hud import Environment

    env = Environment("specter-eval")

    @env.tool()
    def get_test_subjects() -> list[dict[str, str]]:
        """Return the list of known test subjects for evaluation."""
        return KNOWN_SUBJECTS

    @env.scenario("dossier-quality")
    async def dossier_quality_scenario(person_name: str, min_score: float = 0.6):
        """Evaluate dossier quality for a person.

        Yields the person name as the prompt, then scores the dossier output.
        """
        prompt = f"Generate a complete intelligence dossier for: {person_name}"
        response = yield prompt

        # Score the response (in real HUD flow, the agent produces the dossier)
        # For our harness, we run the pipeline directly and score
        dossier = await run_pipeline_for_subject(person_name)
        if dossier is None:
            yield 0.0
            return

        completeness, _ = score_completeness(dossier)
        accuracy, _ = await score_accuracy(dossier)
        synthesis, _ = score_synthesis(dossier)

        overall = (completeness * 0.4) + (accuracy * 0.3) + (synthesis * 0.3)
        yield overall

    HUD_AVAILABLE = True
except ImportError:
    HUD_AVAILABLE = False
    logger.info("HUD SDK not installed — running in standalone mode")


# ---------------------------------------------------------------------------
# Known test subjects (public figures with verifiable data)
# ---------------------------------------------------------------------------

KNOWN_SUBJECTS = [
    {
        "name": "Sam Altman",
        "expected_title": "CEO",
        "expected_company": "OpenAI",
        "expected_social": "twitter",
    },
    {
        "name": "Dario Amodei",
        "expected_title": "CEO",
        "expected_company": "Anthropic",
        "expected_social": "twitter",
    },
    {
        "name": "Garry Tan",
        "expected_title": "President",
        "expected_company": "Y Combinator",
        "expected_social": "twitter",
    },
]


# ---------------------------------------------------------------------------
# Standalone eval runner (no HUD platform needed)
# ---------------------------------------------------------------------------

async def evaluate_person(person_name: str) -> EvalScores:
    """Run full eval for a single person. Returns EvalScores."""
    t0 = time.monotonic()
    logger.info("Evaluating pipeline output for: {}", person_name)

    dossier = await run_pipeline_for_subject(person_name)
    if dossier is None:
        return EvalScores(
            subject_name=person_name,
            details={"error": "pipeline returned no dossier"},
            elapsed_s=time.monotonic() - t0,
        )

    completeness, comp_details = score_completeness(dossier)
    accuracy, acc_details = await score_accuracy(dossier)
    synthesis, synth_details = score_synthesis(dossier)

    overall = (completeness * 0.4) + (accuracy * 0.3) + (synthesis * 0.3)

    return EvalScores(
        subject_name=person_name,
        completeness=completeness,
        accuracy=accuracy,
        synthesis=synthesis,
        overall=overall,
        details={
            "completeness": comp_details,
            "accuracy": acc_details,
            "synthesis": synth_details,
            "dossier_summary": dossier.summary[:200] if dossier.summary else "",
            "work_history_count": len(dossier.work_history),
            "education_count": len(dossier.education),
        },
        elapsed_s=time.monotonic() - t0,
    )


async def run_all_subjects(subjects: list[dict[str, str]] | None = None) -> list[EvalScores]:
    """Evaluate the pipeline for all test subjects. Returns list of scores."""
    subjects = subjects or KNOWN_SUBJECTS
    results: list[EvalScores] = []

    for subject in subjects:
        scores = await evaluate_person(subject["name"])
        results.append(scores)
        _print_scores(scores)

    _print_summary(results)
    return results


def _print_scores(scores: EvalScores) -> None:
    """Pretty-print evaluation scores for one subject."""
    status = "PASS" if scores.overall >= 0.6 else "FAIL"
    logger.info(
        "[{}] {} — overall={:.0%} completeness={:.0%} accuracy={:.0%} synthesis={:.0%} ({:.1f}s)",
        status,
        scores.subject_name,
        scores.overall,
        scores.completeness,
        scores.accuracy,
        scores.synthesis,
        scores.elapsed_s,
    )


def _print_summary(results: list[EvalScores]) -> None:
    """Print aggregate summary."""
    if not results:
        logger.warning("No eval results to summarize")
        return

    avg_overall = sum(r.overall for r in results) / len(results)
    avg_completeness = sum(r.completeness for r in results) / len(results)
    avg_accuracy = sum(r.accuracy for r in results) / len(results)
    avg_synthesis = sum(r.synthesis for r in results) / len(results)
    passed = sum(1 for r in results if r.overall >= 0.6)

    logger.info("=" * 60)
    logger.info(
        "SUMMARY: {}/{} passed | avg_overall={:.0%} comp={:.0%} acc={:.0%} synth={:.0%}",
        passed,
        len(results),
        avg_overall,
        avg_completeness,
        avg_accuracy,
        avg_synthesis,
    )
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="SPECTER Pipeline Eval Harness")
    parser.add_argument("--name", type=str, help="Evaluate a single person by name")
    parser.add_argument(
        "--hud", action="store_true",
        help="Run via HUD platform scenarios (requires HUD_API_KEY)",
    )
    args = parser.parse_args()

    if args.name:
        scores = asyncio.run(evaluate_person(args.name))
        _print_scores(scores)
    else:
        asyncio.run(run_all_subjects())


if __name__ == "__main__":
    main()
