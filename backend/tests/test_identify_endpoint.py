from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from pipeline import PipelineResult


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.fixture
async def client(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── POST /api/capture/identify ──


@pytest.mark.anyio
async def test_identify_success(client: AsyncClient) -> None:
    """Identify endpoint downloads image and returns pipeline result."""
    fake_result = PipelineResult(
        capture_id="identify_abc123",
        total_frames=1,
        faces_detected=1,
        persons_created=["person_abc123"],
        persons_enriched=1,
        success=True,
    )

    # Mock httpx.AsyncClient.get to return fake image data
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.content = b"\xff\xd8\xff\xe0fake_jpeg_data"
    mock_response.raise_for_status = lambda: None

    with (
        patch("main.httpx.AsyncClient") as mock_httpx_cls,
        patch("main.pipeline.process", new_callable=AsyncMock, return_value=fake_result),
    ):
        mock_httpx_instance = AsyncMock()
        mock_httpx_instance.get = AsyncMock(return_value=mock_response)
        mock_httpx_instance.__aenter__ = AsyncMock(return_value=mock_httpx_instance)
        mock_httpx_instance.__aexit__ = AsyncMock(return_value=None)
        mock_httpx_cls.return_value = mock_httpx_instance

        resp = await client.post(
            "/api/capture/identify",
            json={"name": "Sam Altman", "image_url": "https://example.com/sam.jpg"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["faces_detected"] == 1
    assert len(data["persons_created"]) == 1


@pytest.mark.anyio
async def test_identify_missing_name(client: AsyncClient) -> None:
    """Identify endpoint should reject request without name."""
    resp = await client.post(
        "/api/capture/identify",
        json={"image_url": "https://example.com/photo.jpg"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_identify_missing_url(client: AsyncClient) -> None:
    """Identify endpoint should reject request without image_url."""
    resp = await client.post(
        "/api/capture/identify",
        json={"name": "Test Person"},
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_identify_empty_name(client: AsyncClient) -> None:
    """Identify endpoint should reject empty name."""
    resp = await client.post(
        "/api/capture/identify",
        json={"name": "", "image_url": "https://example.com/photo.jpg"},
    )
    assert resp.status_code == 422


# ── GET /api/person/{person_id} ──


@pytest.mark.anyio
async def test_get_person_found(client: AsyncClient) -> None:
    """Get person endpoint returns stored person data."""
    mock_person = {
        "person_id": "person_abc123",
        "name": "Sam Altman",
        "status": "enriched",
        "summary": "CEO of OpenAI",
        "dossier": {"summary": "CEO of OpenAI", "title": "CEO"},
    }

    with patch("main.db_gateway.get_person", new_callable=AsyncMock, return_value=mock_person):
        resp = await client.get("/api/person/person_abc123")

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Sam Altman"
    assert data["dossier"]["title"] == "CEO"


@pytest.mark.anyio
async def test_get_person_not_found(client: AsyncClient) -> None:
    """Get person endpoint returns 404 for unknown person_id."""
    with patch("main.db_gateway.get_person", new_callable=AsyncMock, return_value=None):
        resp = await client.get("/api/person/nonexistent_id")

    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]
