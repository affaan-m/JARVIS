# RESEARCH: hud-python 0.5.29 (HUD SDK), httpx (bundled), pydantic (project dep)
# DECISION: Custom eval harness using HUD Environment + scenarios for pipeline quality
# ALT: Pure pytest scoring — simpler but no HUD platform integration or A/B testing
"""
JARVIS Pipeline Eval Harness
=============================

Evaluates dossier output quality across three axes:
  1. Completeness — does the dossier have work history, education, social profiles?
  2. Accuracy     — do URLs actually resolve?
  3. Synthesis    — is the summary coherent and non-empty?

Enhanced: now runs the full DeepResearcher pipeline (not just Exa) and measures
information density, false positive rate, and per-phase timing.

Usage:
    python -m eval.hud_eval                      # run all test subjects
    python -m eval.hud_eval --name "Sam Altman"  # run one subject
    python -m eval.hud_eval --full-pipeline       # use DeepResearcher (default)
    python -m eval.hud_eval --exa-only            # legacy Exa-only mode
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
    info_density: float = 0.0
    false_positive_rate: float = 0.0
    phase_timings: dict[str, float] = field(default_factory=dict)
    sources_count: int = 0
    urls_discovered: int = 0
    platforms_covered: int = 0


def score_completeness(dossier: DossierReport) -> tuple[float, dict[str, bool]]:
    """Score how complete a dossier is (0.0 - 1.0)."""
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


async def score_accuracy(dossier: DossierReport, timeout: float = 10.0) -> tuple[float, dict[str, bool]]:  # noqa: E501
    """Score URL accuracy by checking if social profile URLs resolve (2xx/3xx)."""
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
        headers={"User-Agent": "JARVIS-Eval/1.0"},
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
    """Score synthesis quality: summary length, specificity, risk flags sanity."""
    details: dict[str, object] = {}
    points = 0.0
    max_points = 5.0

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

    hooks_count = len(dossier.conversation_hooks)
    if hooks_count >= 2:
        points += 1.0
        details["hooks_quality"] = "good"
    elif hooks_count == 1:
        points += 0.5
        details["hooks_quality"] = "minimal"
    else:
        details["hooks_quality"] = "missing"

    wh_count = len(dossier.work_history)
    if wh_count >= 2:
        points += 1.0
        details["work_history_depth"] = "good"
    elif wh_count == 1:
        points += 0.5
        details["work_history_depth"] = "minimal"
    else:
        details["work_history_depth"] = "missing"

    rf_count = len(dossier.risk_flags)
    if rf_count <= 5:
        points += 1.0
        details["risk_flags_sanity"] = "ok"
    else:
        points += 0.5
        details["risk_flags_sanity"] = "excessive"
    details["risk_flags_count"] = rf_count

    return points / max_points, details


def score_info_density(snippets: list[str]) -> float:
    """Score information density — ratio of unique facts to total snippets.

    Higher density = each source contributes unique info (less redundancy).
    """
    if not snippets:
        return 0.0

    # Simple dedup: count unique non-trivial snippets (>20 chars)
    unique = set()
    for s in snippets:
        normalized = s.strip().lower()[:100]
        if len(normalized) > 20:
            unique.add(normalized)

    return len(unique) / len(snippets) if snippets else 0.0


def compute_false_positive_rate(
    snippets: list[str], person_name: str
) -> float:
    """Estimate false positive rate — fraction of snippets NOT about the person."""
    if not snippets:
        return 0.0

    name_parts = person_name.lower().split()
    false_positives = 0

    for snippet in snippets:
        text = snippet.lower()
        if not any(part in text for part in name_parts):
            false_positives += 1

    return false_positives / len(snippets)


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

async def run_pipeline_for_subject(
    person_name: str, *, use_deep_researcher: bool = True
) -> tuple[DossierReport | None, dict[str, object]]:
    """Run the enrichment + synthesis pipeline for a person.

    Returns (dossier, pipeline_metadata).
    When use_deep_researcher=True, runs the full DeepResearcher pipeline
    including SixtyFour.ai, Browser Use skills, and verification.
    """
    settings = get_settings()
    pipeline_meta: dict[str, object] = {}
    all_snippets: list[str] = []
    all_urls: list[str] = []
    sources: set[str] = set()
    platforms: set[str] = set()

    exa_result = None

    if use_deep_researcher and settings.browser_use_api_key:
        # Full pipeline: DeepResearcher
        from agents.deep_researcher import DeepResearcher
        from agents.models import ResearchRequest

        researcher = DeepResearcher(settings)
        request = ResearchRequest(person_name=person_name)

        t_research = time.monotonic()
        agent_results = []
        async for result in researcher.research(request):
            # Extract phase timings from the meta result
            if result.agent_name == "deep_researcher_meta":
                import json as _json
                for snippet in result.snippets:
                    if snippet.startswith("phase_timings:"):
                        try:
                            pipeline_meta["phase_timings"] = _json.loads(
                                snippet.removeprefix("phase_timings:")
                            )
                        except (ValueError, _json.JSONDecodeError):
                            pass
                continue
            agent_results.append(result)
            all_snippets.extend(result.snippets)
            all_urls.extend(result.urls_found)
            sources.add(result.agent_name)
            for p in result.profiles:
                platforms.add(p.platform)

        pipeline_meta["research_elapsed_s"] = round(
            time.monotonic() - t_research, 2
        )
        pipeline_meta["agent_count"] = len(agent_results)

        # Build synthesis request from deep researcher results
        from agents.models import OrchestratorResult
        from pipeline import CapturePipeline

        browser_result = OrchestratorResult(
            person_name=person_name,
            agent_results={r.agent_name: r for r in agent_results},
            all_profiles=[p for r in agent_results for p in r.profiles],
            all_snippets=all_snippets,
            success=bool(agent_results),
        )

        # Also run Exa for the synthesis merge
        if settings.exa_api_key:
            from enrichment.exa_client import ExaEnrichmentClient
            from enrichment.models import EnrichmentRequest

            exa_client = ExaEnrichmentClient(settings)
            exa_result = await exa_client.enrich_person(
                EnrichmentRequest(name=person_name),
            )
            if not exa_result.success:
                exa_result = None

        synthesis_request = CapturePipeline._merge_to_synthesis_request(
            person_name, exa_result, browser_result,
        )
    else:
        # Legacy: Exa-only mode
        if settings.exa_api_key:
            from enrichment.exa_client import ExaEnrichmentClient
            from enrichment.models import EnrichmentRequest

            exa_client = ExaEnrichmentClient(settings)
            exa_result = await exa_client.enrich_person(
                EnrichmentRequest(name=person_name),
            )
            if not exa_result.success:
                logger.warning(
                    "Exa enrichment failed for {}: {}",
                    person_name,
                    exa_result.error,
                )
                exa_result = None

        from pipeline import CapturePipeline
        synthesis_request = CapturePipeline._merge_to_synthesis_request(
            person_name, exa_result, None,
        )

    # Synthesize
    from synthesis.anthropic_engine import AnthropicSynthesisEngine
    engine = AnthropicSynthesisEngine(settings)

    if not engine.configured:
        from synthesis.engine import GeminiSynthesisEngine
        gemini = GeminiSynthesisEngine(settings)
        result = await gemini.synthesize(synthesis_request)
    else:
        result = await engine.synthesize(synthesis_request)

    if not result.success:
        logger.error("Synthesis failed for {}: {}", person_name, result.error)
        return None, pipeline_meta

    pipeline_meta["snippets_count"] = len(all_snippets)
    pipeline_meta["urls_discovered"] = len(set(all_urls))
    pipeline_meta["sources"] = list(sources)
    pipeline_meta["platforms_covered"] = list(platforms)
    pipeline_meta["info_density"] = score_info_density(all_snippets)
    pipeline_meta["false_positive_rate"] = compute_false_positive_rate(
        all_snippets, person_name
    )

    return result.dossier, pipeline_meta


# ---------------------------------------------------------------------------
# HUD Environment (eval scenarios)
# ---------------------------------------------------------------------------

try:
    from hud import Environment

    env = Environment("jarvis-eval")

    @env.tool()
    def get_test_subjects() -> list[dict[str, str]]:
        """Return the list of known test subjects for evaluation."""
        return KNOWN_SUBJECTS

    @env.scenario("dossier-quality")
    async def dossier_quality_scenario(person_name: str, min_score: float = 0.6):
        """Evaluate dossier quality for a person."""
        prompt = f"Generate a complete intelligence dossier for: {person_name}"
        _response = yield prompt

        dossier, _ = await run_pipeline_for_subject(person_name)
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
    {
        "name": "Affaan Mustafa",
        "expected_title": "Founder",
        "expected_company": "Ito",
        "expected_social": "twitter",
    },
]


# ---------------------------------------------------------------------------
# Standalone eval runner (no HUD platform needed)
# ---------------------------------------------------------------------------

async def evaluate_person(
    person_name: str, *, use_deep_researcher: bool = True
) -> EvalScores:
    """Run full eval for a single person. Returns EvalScores."""
    t0 = time.monotonic()
    logger.info("Evaluating pipeline output for: {}", person_name)

    dossier, pipeline_meta = await run_pipeline_for_subject(
        person_name, use_deep_researcher=use_deep_researcher
    )
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

    info_density = pipeline_meta.get("info_density", 0.0)
    false_positive_rate = pipeline_meta.get("false_positive_rate", 0.0)
    urls_discovered = pipeline_meta.get("urls_discovered", 0)
    platforms = pipeline_meta.get("platforms_covered", [])
    raw_phase_timings = pipeline_meta.get("phase_timings", {})

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
            "pipeline": pipeline_meta,
        },
        elapsed_s=time.monotonic() - t0,
        info_density=info_density,
        false_positive_rate=false_positive_rate,
        phase_timings={k: float(v) for k, v in raw_phase_timings.items()} if isinstance(raw_phase_timings, dict) else {},  # noqa: E501
        sources_count=len(pipeline_meta.get("sources", [])),
        urls_discovered=urls_discovered,
        platforms_covered=len(platforms),
    )


async def run_all_subjects(
    subjects: list[dict[str, str]] | None = None,
    *,
    use_deep_researcher: bool = True,
) -> list[EvalScores]:
    """Evaluate the pipeline for all test subjects. Returns list of scores."""
    subjects = subjects or KNOWN_SUBJECTS
    results: list[EvalScores] = []

    for subject in subjects:
        scores = await evaluate_person(
            subject["name"], use_deep_researcher=use_deep_researcher
        )
        results.append(scores)
        _print_scores(scores)

    _print_summary(results)
    return results


def _print_scores(scores: EvalScores) -> None:
    """Pretty-print evaluation scores for one subject."""
    status = "PASS" if scores.overall >= 0.6 else "FAIL"
    logger.info(
        "[{}] {} — overall={:.0%} completeness={:.0%} accuracy={:.0%} synthesis={:.0%} "
        "density={:.0%} fp_rate={:.0%} sources={} urls={} platforms={} ({:.1f}s)",
        status,
        scores.subject_name,
        scores.overall,
        scores.completeness,
        scores.accuracy,
        scores.synthesis,
        scores.info_density,
        scores.false_positive_rate,
        scores.sources_count,
        scores.urls_discovered,
        scores.platforms_covered,
        scores.elapsed_s,
    )
    if scores.phase_timings:
        timings_str = " | ".join(
            f"{k}={v:.1f}s" for k, v in sorted(scores.phase_timings.items())
        )
        logger.info("         phases: {}", timings_str)


def _print_summary(results: list[EvalScores]) -> None:
    """Print aggregate summary."""
    if not results:
        logger.warning("No eval results to summarize")
        return

    avg_overall = sum(r.overall for r in results) / len(results)
    avg_completeness = sum(r.completeness for r in results) / len(results)
    avg_accuracy = sum(r.accuracy for r in results) / len(results)
    avg_synthesis = sum(r.synthesis for r in results) / len(results)
    avg_density = sum(r.info_density for r in results) / len(results)
    avg_fp = sum(r.false_positive_rate for r in results) / len(results)
    avg_urls = sum(r.urls_discovered for r in results) / len(results)
    avg_platforms = sum(r.platforms_covered for r in results) / len(results)
    passed = sum(1 for r in results if r.overall >= 0.6)

    logger.info("=" * 70)
    logger.info(
        "SUMMARY: {}/{} passed | overall={:.0%} comp={:.0%} acc={:.0%} synth={:.0%}",
        passed, len(results), avg_overall, avg_completeness, avg_accuracy, avg_synthesis,
    )
    logger.info(
        "         density={:.0%} fp_rate={:.0%} avg_urls={:.0f} avg_platforms={:.0f}",
        avg_density, avg_fp, avg_urls, avg_platforms,
    )
    logger.info("=" * 70)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS Pipeline Eval Harness")
    parser.add_argument("--name", type=str, help="Evaluate a single person by name")
    parser.add_argument(
        "--hud", action="store_true",
        help="Run via HUD platform scenarios (requires HUD_API_KEY)",
    )
    parser.add_argument(
        "--exa-only", action="store_true",
        help="Legacy mode: use Exa only (no Browser Use skills)",
    )
    parser.add_argument(
        "--full-pipeline", action="store_true", default=True,
        help="Use full DeepResearcher pipeline (default)",
    )
    args = parser.parse_args()

    use_deep = not args.exa_only

    if args.name:
        scores = asyncio.run(
            evaluate_person(args.name, use_deep_researcher=use_deep)
        )
        _print_scores(scores)
    else:
        asyncio.run(run_all_subjects(use_deep_researcher=use_deep))


if __name__ == "__main__":
    main()
