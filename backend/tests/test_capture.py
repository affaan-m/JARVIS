from __future__ import annotations

import io

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_capture_upload_returns_processed() -> None:
    file = io.BytesIO(b"fake image data")
    response = client.post(
        "/api/capture",
        files={"file": ("test.jpg", file, "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in ("processed", "error")
    assert payload["filename"] == "test.jpg"
    assert payload["content_type"] == "image/jpeg"


def test_capture_upload_returns_capture_id() -> None:
    file = io.BytesIO(b"fake image data")
    response = client.post(
        "/api/capture",
        files={"file": ("photo.png", file, "image/png")},
    )

    payload = response.json()
    assert payload["capture_id"].startswith("cap_")
    assert len(payload["capture_id"]) == 16  # "cap_" + 12 hex chars


def test_capture_upload_default_source() -> None:
    file = io.BytesIO(b"fake image data")
    response = client.post(
        "/api/capture",
        files={"file": ("test.jpg", file, "image/jpeg")},
    )

    payload = response.json()
    assert payload["source"] == "manual_upload"


def test_capture_upload_custom_source() -> None:
    file = io.BytesIO(b"fake image data")
    response = client.post(
        "/api/capture",
        files={"file": ("test.jpg", file, "image/jpeg")},
        params={"source": "telegram"},
    )

    payload = response.json()
    assert payload["source"] == "telegram"


def test_capture_upload_generates_unique_ids() -> None:
    file1 = io.BytesIO(b"data1")
    file2 = io.BytesIO(b"data2")

    r1 = client.post("/api/capture", files={"file": ("a.jpg", file1, "image/jpeg")})
    r2 = client.post("/api/capture", files={"file": ("b.jpg", file2, "image/jpeg")})

    assert r1.json()["capture_id"] != r2.json()["capture_id"]


def test_capture_upload_without_file_returns_422() -> None:
    response = client.post("/api/capture")

    assert response.status_code == 422


def test_capture_upload_video_file() -> None:
    file = io.BytesIO(b"fake video data")
    response = client.post(
        "/api/capture",
        files={"file": ("clip.mp4", file, "video/mp4")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "clip.mp4"
    assert payload["content_type"] == "video/mp4"


def test_capture_upload_includes_pipeline_fields() -> None:
    file = io.BytesIO(b"fake image data")
    response = client.post(
        "/api/capture",
        files={"file": ("test.jpg", file, "image/jpeg")},
    )

    payload = response.json()
    assert "total_frames" in payload
    assert "faces_detected" in payload
    assert "persons_created" in payload
    assert isinstance(payload["total_frames"], int)
    assert isinstance(payload["faces_detected"], int)
    assert isinstance(payload["persons_created"], list)
