from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from config import Settings
from db.convex_client import ConvexGateway
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest
from observability.laminar import initialize_laminar, traced

# --- ConvexGateway ---


def test_convex_gateway_not_configured() -> None:
    gw = ConvexGateway(Settings())
    assert gw.configured is False


def test_convex_gateway_configured_with_url() -> None:
    gw = ConvexGateway(Settings(CONVEX_URL="https://convex.example.com"))
    assert gw.configured is True


@pytest.mark.anyio
async def test_convex_store_person_unconfigured_raises() -> None:
    gw = ConvexGateway(Settings())
    with pytest.raises(RuntimeError, match="not configured"):
        await gw.store_person("p1", {"name": "Alice"})


@pytest.mark.anyio
async def test_convex_get_person_unconfigured_raises() -> None:
    gw = ConvexGateway(Settings())
    with pytest.raises(RuntimeError, match="not configured"):
        await gw.get_person("p1")


@pytest.mark.anyio
async def test_convex_update_person_unconfigured_raises() -> None:
    gw = ConvexGateway(Settings())
    with pytest.raises(RuntimeError, match="not configured"):
        await gw.update_person("p1", {"name": "Updated"})


@pytest.mark.anyio
async def test_convex_store_capture_unconfigured_raises() -> None:
    gw = ConvexGateway(Settings())
    with pytest.raises(RuntimeError, match="not configured"):
        await gw.store_capture("c1", {"source": "camera"})


@pytest.mark.anyio
async def test_convex_store_person_configured_returns_id() -> None:
    gw = ConvexGateway(Settings(CONVEX_URL="https://convex.example.com"))
    gw._mutation = AsyncMock(return_value="p1")
    result = await gw.store_person("p1", {"name": "Alice"})
    assert result == "p1"
    gw._mutation.assert_called_once()


@pytest.mark.anyio
async def test_convex_get_person_configured_returns_none() -> None:
    gw = ConvexGateway(Settings(CONVEX_URL="https://convex.example.com"))
    gw._query = AsyncMock(return_value=None)
    result = await gw.get_person("p1")
    assert result is None
    gw._query.assert_called_once()


@pytest.mark.anyio
async def test_convex_update_person_configured() -> None:
    gw = ConvexGateway(Settings(CONVEX_URL="https://convex.example.com"))
    gw._mutation = AsyncMock(return_value=None)
    await gw.update_person("p1", {"status": "enriched"})
    gw._mutation.assert_called_once_with(
        "persons:update", {"person_id": "p1", "data": {"status": "enriched"}},
    )


@pytest.mark.anyio
async def test_convex_store_capture_configured_returns_id() -> None:
    gw = ConvexGateway(Settings(CONVEX_URL="https://convex.example.com"))
    gw._mutation = AsyncMock(return_value="c1")
    result = await gw.store_capture("c1", {"source": "camera"})
    assert result == "c1"
    gw._mutation.assert_called_once()


@pytest.mark.anyio
async def test_convex_store_person_strips_embedding() -> None:
    gw = ConvexGateway(Settings(CONVEX_URL="https://convex.example.com"))
    gw._mutation = AsyncMock(return_value="p1")
    await gw.store_person("p1", {"name": "Alice", "embedding": [0.1] * 512})
    call_args = gw._mutation.call_args[0][1]
    assert "embedding" not in call_args["data"]
    assert call_args["data"]["person_id"] == "p1"


# --- ExaEnrichmentClient ---


def test_exa_client_not_configured() -> None:
    client = ExaEnrichmentClient(Settings())
    assert client.configured is False


def test_exa_client_configured() -> None:
    client = ExaEnrichmentClient(Settings(EXA_API_KEY="test-key"))
    assert client.configured is True


def test_exa_build_person_query_name_only() -> None:
    client = ExaEnrichmentClient(Settings())
    q = client.build_person_query("John Doe")
    assert q == '"John Doe"'


def test_exa_build_person_query_with_company() -> None:
    client = ExaEnrichmentClient(Settings())
    q = client.build_person_query("John Doe", "Acme")
    assert q == '"John Doe" "Acme"'


@pytest.mark.anyio
async def test_exa_enrich_person_unconfigured() -> None:
    client = ExaEnrichmentClient(Settings())
    result = await client.enrich_person(EnrichmentRequest(name="Test User"))
    assert result.success is False
    assert "not configured" in result.error


@pytest.mark.anyio
async def test_exa_enrich_person_configured() -> None:
    client = ExaEnrichmentClient(Settings(EXA_API_KEY="test-key"))
    mock_result = SimpleNamespace(
        title="Test User - LinkedIn",
        url="https://linkedin.com/in/testuser",
        text="Test User is a developer.",
        highlights=["developer"],
        score=0.9,
    )
    mock_response = SimpleNamespace(results=[mock_result])
    mock_exa = MagicMock()
    mock_exa.search_and_contents.return_value = mock_response
    client._client = mock_exa

    result = await client.enrich_person(EnrichmentRequest(name="Test User"))
    assert result.success is True
    assert len(result.hits) == 1
    assert result.hits[0].source == "exa"


# --- Laminar Observability ---


def test_laminar_initialize_returns_false_when_unconfigured() -> None:
    import observability.laminar as lam_mod

    lam_mod._initialized = False
    result = initialize_laminar(Settings())
    assert result is False


def test_traced_async_noop_without_initialization() -> None:
    import asyncio

    import observability.laminar as lam_mod

    lam_mod._initialized = False

    @traced("test.async_noop")
    async def dummy() -> str:
        return "ok"

    assert asyncio.run(dummy()) == "ok"


def test_traced_sync_noop_without_initialization() -> None:
    import observability.laminar as lam_mod

    lam_mod._initialized = False

    @traced("test.sync_noop")
    def dummy() -> str:
        return "sync_ok"

    assert dummy() == "sync_ok"
