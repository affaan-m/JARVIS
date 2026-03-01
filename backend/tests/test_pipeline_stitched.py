"""Integration test for main.py pipeline wiring.

Verifies that enrichment, orchestrator, and synthesis components are injected
into the CapturePipeline when env vars are set, and omitted when missing.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Clear lru_cache between tests so Settings picks up patched env."""
    from config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _import_main_fresh():
    """Force-reimport main to pick up patched settings."""
    import importlib

    import main

    importlib.reload(main)
    return main


class TestPipelineWiring:
    def test_pipeline_has_enrichment_when_keys_set(self) -> None:
        """When EXA_API_KEY and GEMINI_API_KEY are set, pipeline gets enrichment deps."""
        env = {
            "EXA_API_KEY": "test-exa-key",
            "GEMINI_API_KEY": "test-gemini-key",
            "BROWSER_USE_API_KEY": "test-browser-key",
        }
        with patch.dict("os.environ", env, clear=False):
            m = _import_main_fresh()

            assert m.exa_client is not None
            assert m.orchestrator is not None
            assert m.synthesis_engine is not None
            assert m.pipeline._exa is not None
            assert m.pipeline._orchestrator is not None
            assert m.pipeline._synthesis is not None

    def test_pipeline_no_enrichment_when_keys_missing(self) -> None:
        """When API keys are missing, pipeline runs without enrichment deps."""
        env = {
            "EXA_API_KEY": "",
            "GEMINI_API_KEY": "",
            "BROWSER_USE_API_KEY": "",
        }
        with patch.dict("os.environ", env, clear=False):
            m = _import_main_fresh()

            assert m.exa_client is None
            assert m.orchestrator is None
            assert m.synthesis_engine is None
            assert m.pipeline._exa is None
            assert m.pipeline._orchestrator is None
            assert m.pipeline._synthesis is None

    def test_convex_gateway_used_when_url_set(self) -> None:
        """When CONVEX_URL is set, ConvexGateway is used instead of InMemory."""
        from db.convex_client import ConvexGateway

        env = {"CONVEX_URL": "https://test.convex.cloud"}
        with patch.dict("os.environ", env, clear=False):
            m = _import_main_fresh()

            assert isinstance(m.db_gateway, ConvexGateway)

    def test_inmemory_gateway_used_when_no_convex(self) -> None:
        """When CONVEX_URL is missing, InMemoryDatabaseGateway is used."""
        from db.memory_gateway import InMemoryDatabaseGateway

        env = {"CONVEX_URL": ""}
        with patch.dict("os.environ", env, clear=False):
            m = _import_main_fresh()

            assert isinstance(m.db_gateway, InMemoryDatabaseGateway)
