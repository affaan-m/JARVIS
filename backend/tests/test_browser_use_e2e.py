"""End-to-end test for Browser Use cloud API integration.

Tests that the browser agents actually work against the live Browser Use cloud API.
Run with:  .venv/bin/python -m pytest tests/test_browser_use_e2e.py -v -s
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest
from loguru import logger

# Configure loguru for clear test output
logger.remove()
logger.add(sys.stderr, level="DEBUG", format="{time:HH:mm:ss} | {level:<7} | {message}")


def _get_settings():
    from config import Settings

    return Settings()


def _require_live_browser_use():
    if os.getenv("RUN_BROWSER_USE_E2E") != "1":
        pytest.skip("Browser Use live E2E tests are opt-in; set RUN_BROWSER_USE_E2E=1")

    settings = _get_settings()
    if not settings.browser_use_api_key:
        pytest.skip("BROWSER_USE_API_KEY not set")
    return settings


def test_browser_use_sdk_imports():
    """Verify browser-use SDK is installed and importable."""
    from browser_use import Agent, Browser, ChatBrowserUse

    assert Agent is not None
    assert Browser is not None
    assert ChatBrowserUse is not None
    logger.info("SDK imports OK: Agent, Browser, ChatBrowserUse")


def test_api_key_configured():
    """Verify BROWSER_USE_API_KEY is set in environment."""
    settings = _require_live_browser_use()
    logger.info("BROWSER_USE_API_KEY is configured (length={})", len(settings.browser_use_api_key))


def test_google_agent_single_query():
    """Run GoogleAgent with a real person query against Browser Use cloud API."""
    from agents.google_agent import GoogleAgent
    from agents.models import AgentStatus, ResearchRequest

    settings = _require_live_browser_use()

    agent = GoogleAgent(settings)
    assert agent.configured, "GoogleAgent reports not configured"

    request = ResearchRequest(
        person_name="Elon Musk",
        company="Tesla",
        timeout_seconds=180.0,
    )

    logger.info("--- Starting GoogleAgent e2e test ---")
    start = time.monotonic()
    result = asyncio.run(agent.run(request))
    elapsed = time.monotonic() - start

    logger.info("GoogleAgent result: status={} elapsed={:.1f}s", result.status.value, elapsed)
    logger.info("  profiles: {}", len(result.profiles))
    logger.info("  snippets: {}", len(result.snippets))
    logger.info("  urls_found: {}", len(result.urls_found))
    if result.error:
        logger.error("  error: {}", result.error)
    if result.snippets:
        for i, s in enumerate(result.snippets[:3]):
            logger.info("  snippet[{}]: {}...", i, s[:200])

    assert result.status in (AgentStatus.SUCCESS, AgentStatus.TIMEOUT), (
        f"GoogleAgent failed: {result.error}"
    )
    if result.status == AgentStatus.SUCCESS:
        assert len(result.snippets) > 0, "GoogleAgent returned SUCCESS but no snippets"
    logger.info("--- GoogleAgent e2e test PASSED ---")


def test_orchestrator_fan_out():
    """Run the full orchestrator with all agents in parallel."""
    from agents.models import AgentStatus, ResearchRequest
    from agents.orchestrator import ResearchOrchestrator

    settings = _require_live_browser_use()

    orchestrator = ResearchOrchestrator(settings)
    logger.info("Orchestrator agents: {}", orchestrator.agent_names)

    request = ResearchRequest(
        person_name="Sam Altman",
        company="OpenAI",
        timeout_seconds=180.0,
    )

    logger.info("--- Starting orchestrator fan-out e2e test ---")
    start = time.monotonic()
    result = asyncio.run(orchestrator.research_person(request))
    elapsed = time.monotonic() - start

    logger.info("Orchestrator result: success={} elapsed={:.1f}s", result.success, elapsed)
    logger.info("  total profiles: {}", len(result.all_profiles))
    logger.info("  total snippets: {}", len(result.all_snippets))

    for name, agent_result in result.agent_results.items():
        status_icon = "OK" if agent_result.status == AgentStatus.SUCCESS else "FAIL"
        logger.info(
            "  agent={:<12} status={:<8} profiles={} snippets={} time={:.1f}s err={}",
            name,
            f"[{status_icon}]",
            len(agent_result.profiles),
            len(agent_result.snippets),
            agent_result.duration_seconds,
            agent_result.error or "none",
        )

    # At least one agent should succeed
    assert result.success, (
        "All agents failed. Results:\n"
        + "\n".join(
            f"  {n}: {r.status.value} - {r.error}" for n, r in result.agent_results.items()
        )
    )
    logger.info("--- Orchestrator fan-out e2e test PASSED ---")


if __name__ == "__main__":
    logger.info("=== Browser Use E2E Test Suite ===\n")

    logger.info("[1/4] Testing SDK imports...")
    test_browser_use_sdk_imports()

    logger.info("\n[2/4] Testing API key configuration...")
    test_api_key_configured()

    logger.info("\n[3/4] Testing single GoogleAgent query (live API call)...")
    test_google_agent_single_query()

    logger.info("\n[4/4] Testing orchestrator fan-out (all agents, live API)...")
    test_orchestrator_fan_out()

    logger.info("\n=== All E2E tests passed ===")
