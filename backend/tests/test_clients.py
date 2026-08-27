from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agents.browser_use_client import BrowserUseClient, BrowserUseError
from config import Settings
from db.convex_client import ConvexGateway
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest
from observability.laminar import initialize_laminar, traced

# --- BrowserUseClient ---


@pytest.mark.anyio
async def test_browser_use_create_run_uses_v4_contract() -> None:
    async def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v4/runs"
        assert request.headers["X-Browser-Use-API-Key"] == "test-key"
        assert not request.url.params
        body = json.loads(request.content)
        assert body == {
            "task": "Open https://example.com first.\nFind the pricing page",
            "browserSettings": {
                "screenWidth": 1280,
                "screenHeight": 800,
                "record": True,
            },
            "maxCostUsd": 0.25,
        }
        return httpx.Response(
            200,
            json={"id": "run-1", "sessionId": "session-1", "status": "queued"},
        )

    client = BrowserUseClient(
        Settings(BROWSER_USE_API_KEY="test-key"),
        transport=httpx.MockTransport(handler),
    )

    result = await client.create_run("Find the pricing page", start_url="https://example.com")

    assert result["id"] == "run-1"
    assert result["sessionId"] == "session-1"


@pytest.mark.anyio
async def test_browser_use_reads_v4_session_run_and_events() -> None:
    async def handler(request):
        responses = {
            "/api/v4/sessions/session-1": {
                "sessionId": "session-1",
                "latestRunId": "run-1",
                "status": "running",
            },
            "/api/v4/runs/run-1": {"id": "run-1", "status": "completed", "result": "ok"},
            "/api/v4/runs/run-1/events": {
                "events": [
                    {
                        "type": "browser.ready",
                        "data": {"live_view_url": "https://live.example/run-1"},
                    }
                ]
            },
        }
        if request.url.path.endswith("/events"):
            assert request.url.params["include_output"] == "false"
        return httpx.Response(200, json=responses[request.url.path])

    client = BrowserUseClient(
        Settings(BROWSER_USE_API_KEY="test-key"),
        transport=httpx.MockTransport(handler),
    )

    session = await client.get_session("session-1")
    run = await client.get_run("run-1")
    events = await client.get_run_events("run-1")

    assert session["latestRunId"] == "run-1"
    assert run["result"] == "ok"
    assert events[0]["data"]["live_view_url"] == "https://live.example/run-1"


@pytest.mark.anyio
async def test_browser_use_raises_typed_error() -> None:
    client = BrowserUseClient(
        Settings(BROWSER_USE_API_KEY="test-key"),
        transport=httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorized")),
    )

    with pytest.raises(BrowserUseError, match="Browser Use API 401: unauthorized"):
        await client.get_run("run-1")


@pytest.mark.anyio
async def test_browser_use_wraps_transport_error() -> None:
    def handler(request):
        raise httpx.ConnectError("connection failed", request=request)

    client = BrowserUseClient(
        Settings(BROWSER_USE_API_KEY="test-key"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(BrowserUseError, match="request failed: ConnectError") as exc_info:
        await client.get_run("run-1")

    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)


@pytest.mark.anyio
async def test_browser_use_wraps_invalid_json() -> None:
    client = BrowserUseClient(
        Settings(BROWSER_USE_API_KEY="test-key"),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not-json")),
    )

    with pytest.raises(BrowserUseError, match="invalid JSON response") as exc_info:
        await client.get_run("run-1")

    assert isinstance(exc_info.value.__cause__, ValueError)


@pytest.mark.anyio
async def test_browser_use_creates_v4_session_share() -> None:
    async def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v4/sessions/session-1/share"
        return httpx.Response(200, json={"shareUrl": "https://cloud.example/share/v4/token"})

    client = BrowserUseClient(
        Settings(BROWSER_USE_API_KEY="test-key"),
        transport=httpx.MockTransport(handler),
    )

    share = await client.make_session_public("session-1")

    assert share["shareUrl"] == "https://cloud.example/share/v4/token"


def test_research_stream_emits_v4_session_before_results(monkeypatch) -> None:
    import asyncio

    from fastapi.testclient import TestClient

    import main as main_module
    from agents.models import AgentResult, AgentStatus

    class FakeBrowserUseClient:
        async def create_run(self, task, start_url=None):
            return {"id": "run-v4", "sessionId": "session-v4"}

    class FakePipeline:
        async def stream_research(self, person_name, person_id):
            await asyncio.sleep(0.01)
            yield AgentResult(
                agent_name="test_agent",
                status=AgentStatus.SUCCESS,
                snippets=["result"],
            )

    class FakeDatabase:
        async def store_person(self, person_id, data):
            return "person-v4"

    monkeypatch.setattr(main_module, "bu_client", FakeBrowserUseClient())
    monkeypatch.setattr(main_module, "deep_researcher", object())
    monkeypatch.setattr(main_module, "pipeline", FakePipeline())
    monkeypatch.setattr(main_module, "db_gateway", FakeDatabase())
    monkeypatch.setattr(main_module, "synthesis_engine", None)

    response = TestClient(main_module.app).get("/api/research/Ada/stream")

    assert response.status_code == 200
    session_position = response.text.index('"live_session_id": "session-v4"')
    result_position = response.text.index('"agent_name":"test_agent"')
    assert session_position < result_position


@pytest.mark.anyio
async def test_research_stream_cancels_pending_work_on_disconnect(monkeypatch) -> None:
    import asyncio

    import main as main_module
    from agents.models import AgentResult, AgentStatus

    never = asyncio.Event()
    browser_started = asyncio.Event()
    browser_cancelled = asyncio.Event()
    research_started = asyncio.Event()
    research_cancelled = asyncio.Event()

    class FakeBrowserUseClient:
        async def create_run(self, task, start_url=None):
            browser_started.set()
            try:
                await never.wait()
            finally:
                browser_cancelled.set()

    class FakePipeline:
        async def stream_research(self, person_name, person_id):
            research_started.set()
            try:
                await never.wait()
                yield AgentResult(agent_name="never", status=AgentStatus.SUCCESS)
            finally:
                research_cancelled.set()

    class FakeDatabase:
        async def store_person(self, person_id, data):
            return "person-v4"

    monkeypatch.setattr(main_module, "bu_client", FakeBrowserUseClient())
    monkeypatch.setattr(main_module, "deep_researcher", object())
    monkeypatch.setattr(main_module, "pipeline", FakePipeline())
    monkeypatch.setattr(main_module, "db_gateway", FakeDatabase())
    monkeypatch.setattr(main_module, "synthesis_engine", None)

    response = await main_module.stream_research("Ada")
    body_iterator = response.body_iterator
    await anext(body_iterator)
    next_event = asyncio.create_task(anext(body_iterator))
    await asyncio.wait_for(browser_started.wait(), timeout=1)
    await asyncio.wait_for(research_started.wait(), timeout=1)

    next_event.cancel()
    with pytest.raises(asyncio.CancelledError):
        await next_event

    assert browser_cancelled.is_set()
    assert research_cancelled.is_set()


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
