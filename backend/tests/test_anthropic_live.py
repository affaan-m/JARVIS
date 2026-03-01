"""Live integration tests for the Anthropic synthesis engine.

These tests call the real Anthropic API and (optionally) Exa API.
They require ANTHROPIC_API_KEY and optionally EXA_API_KEY in .env.

Run with: pytest tests/test_anthropic_live.py -v --no-cov -m live
"""

from __future__ import annotations

import pytest

from config import Settings
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest
from synthesis.anthropic_engine import AnthropicSynthesisEngine
from synthesis.models import SynthesisRequest

settings = Settings()

skip_no_anthropic = pytest.mark.skipif(
    not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY not set",
)
skip_no_exa = pytest.mark.skipif(
    not settings.exa_api_key,
    reason="EXA_API_KEY not set",
)


@pytest.mark.live
@skip_no_anthropic
@pytest.mark.anyio
async def test_live_anthropic_elon_musk() -> None:
    """Call real Anthropic API for Elon Musk — no enrichment, just synthesis from name."""
    engine = AnthropicSynthesisEngine(settings)
    request = SynthesisRequest(
        person_name="Elon Musk",
        enrichment_snippets=[
            "CEO of Tesla and SpaceX",
            "Owner of X (formerly Twitter)",
            "Born in South Africa, moved to US",
        ],
    )

    result = await engine.synthesize(request)

    assert result.success is True, f"Synthesis failed: {result.error}"
    assert result.person_name == "Elon Musk"
    assert result.dossier is not None

    dossier = result.dossier
    print(f"\n--- Elon Musk Dossier ---")
    print(f"Summary: {dossier.summary}")
    print(f"Title: {dossier.title}")
    print(f"Company: {dossier.company}")
    print(f"Work history: {len(dossier.work_history)} entries")
    for wh in dossier.work_history:
        print(f"  - {wh.role} at {wh.company} ({wh.period})")
    print(f"Education: {len(dossier.education)} entries")
    for ed in dossier.education:
        print(f"  - {ed.school}: {ed.degree}")
    print(f"Social profiles: {dossier.social_profiles.model_dump(exclude_none=True)}")
    print(f"Notable activity: {dossier.notable_activity}")
    print(f"Conversation hooks: {dossier.conversation_hooks}")
    print(f"Risk flags: {dossier.risk_flags}")

    # Basic sanity checks on the dossier
    assert len(dossier.summary) > 20
    assert dossier.title is not None
    assert len(dossier.work_history) >= 1
    # Note: social profiles may be None when enrichment_snippets don't contain profile URLs.
    # The model correctly avoids fabricating data per prompt instructions.

    # Verify frontend serialization works
    frontend_dict = dossier.to_frontend_dict()
    assert "workHistory" in frontend_dict
    assert "socialProfiles" in frontend_dict
    assert "conversationHooks" in frontend_dict


@pytest.mark.live
@skip_no_anthropic
@skip_no_exa
@pytest.mark.anyio
async def test_live_exa_into_anthropic_less_famous_person() -> None:
    """Exa enrichment → Anthropic synthesis for a less famous person.

    Tests the full enrichment-to-synthesis flow as it would run in the pipeline.
    """
    exa = ExaEnrichmentClient(settings)
    engine = AnthropicSynthesisEngine(settings)

    # Step 1: Exa enrichment
    exa_result = await exa.enrich_person(EnrichmentRequest(name="Jensen Huang"))

    assert exa_result.success is True, f"Exa enrichment failed: {exa_result.error}"
    assert len(exa_result.hits) > 0

    print(f"\n--- Exa Results for Jensen Huang ---")
    print(f"Hits: {len(exa_result.hits)}")
    for hit in exa_result.hits[:5]:
        print(f"  [{hit.score:.2f}] {hit.title} - {hit.url}")

    # Step 2: Build SynthesisRequest from Exa results
    enrichment_snippets = []
    for hit in exa_result.hits:
        snippet = f"[{hit.title}]({hit.url})"
        if hit.snippet:
            snippet += f" — {hit.snippet}"
        enrichment_snippets.append(snippet)

    request = SynthesisRequest(
        person_name="Jensen Huang",
        enrichment_snippets=enrichment_snippets,
    )

    # Step 3: Anthropic synthesis
    result = await engine.synthesize(request)

    assert result.success is True, f"Synthesis failed: {result.error}"
    assert result.dossier is not None

    dossier = result.dossier
    print(f"\n--- Jensen Huang Dossier ---")
    print(f"Summary: {dossier.summary}")
    print(f"Title: {dossier.title}")
    print(f"Company: {dossier.company}")
    print(f"Work history: {len(dossier.work_history)} entries")
    for wh in dossier.work_history:
        print(f"  - {wh.role} at {wh.company} ({wh.period})")
    print(f"Education: {len(dossier.education)} entries")
    for ed in dossier.education:
        print(f"  - {ed.school}: {ed.degree}")
    print(f"Social profiles: {dossier.social_profiles.model_dump(exclude_none=True)}")
    print(f"Notable activity: {dossier.notable_activity}")
    print(f"Conversation hooks: {dossier.conversation_hooks}")
    print(f"Risk flags: {dossier.risk_flags}")

    # Sanity checks
    assert len(dossier.summary) > 20
    assert dossier.title is not None

    # Frontend serialization
    frontend_dict = dossier.to_frontend_dict()
    assert isinstance(frontend_dict["workHistory"], list)
    assert isinstance(frontend_dict["conversationHooks"], list)
