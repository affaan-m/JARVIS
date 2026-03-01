"""Tests for webhook capture endpoints."""
from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

# 1x1 red PNG pixel as test fixture
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
    b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
_B64_PNG = base64.b64encode(_TINY_PNG).decode()


# ---------- POST /api/capture/webhook ----------


def test_webhook_valid_base64() -> None:
    resp = client.post(
        "/api/capture/webhook",
        json={"image_base64": _B64_PNG, "source": "test_hook"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["capture_id"].startswith("cap_")
    assert body["source"] == "test_hook"
    assert body["status"] in ("processed", "error")


def test_webhook_default_source() -> None:
    resp = client.post(
        "/api/capture/webhook",
        json={"image_base64": _B64_PNG},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "webhook"


def test_webhook_invalid_base64() -> None:
    resp = client.post(
        "/api/capture/webhook",
        json={"image_base64": "!!!not-base64!!!", "source": "bad"},
    )
    assert resp.status_code == 400
    assert "Invalid base64" in resp.json()["detail"]


def test_webhook_empty_base64() -> None:
    resp = client.post(
        "/api/capture/webhook",
        json={"image_base64": "", "source": "empty"},
    )
    assert resp.status_code == 400


def test_webhook_missing_field() -> None:
    resp = client.post("/api/capture/webhook", json={"source": "oops"})
    assert resp.status_code == 422


def test_webhook_returns_pipeline_fields() -> None:
    resp = client.post(
        "/api/capture/webhook",
        json={"image_base64": _B64_PNG},
    )
    body = resp.json()
    assert "total_frames" in body
    assert "faces_detected" in body
    assert "persons_created" in body
    assert isinstance(body["total_frames"], int)
    assert isinstance(body["faces_detected"], int)
    assert isinstance(body["persons_created"], list)


# ---------- POST /api/capture/url ----------


def test_url_missing_url_field() -> None:
    resp = client.post("/api/capture/url", json={"source": "test"})
    assert resp.status_code == 422


def test_url_invalid_url() -> None:
    resp = client.post(
        "/api/capture/url",
        json={"url": "http://localhost:1/nonexistent.jpg", "source": "bad_url"},
    )
    assert resp.status_code == 400
