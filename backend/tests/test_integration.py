from __future__ import annotations

import io

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_capture_response_matches_pipeline_contract() -> None:
    """Integration test: upload a file and verify the full response payload
    matches the pipeline response contract."""
    file = io.BytesIO(b"\x89PNG\r\n\x1a\n fake png header")
    response = client.post(
        "/api/capture",
        files={"file": ("headshot.png", file, "image/png")},
        params={"source": "glasses_cam"},
    )

    assert response.status_code == 200
    payload = response.json()

    # Required fields present
    assert "capture_id" in payload
    assert "filename" in payload
    assert "content_type" in payload
    assert "status" in payload
    assert "source" in payload

    # Values match what was sent
    assert payload["filename"] == "headshot.png"
    assert payload["content_type"] == "image/png"
    assert payload["status"] in ("processed", "error")
    assert payload["source"] == "glasses_cam"

    # capture_id follows expected format
    assert payload["capture_id"].startswith("cap_")
    assert len(payload["capture_id"]) == 16

    # Pipeline fields present
    assert "total_frames" in payload
    assert "faces_detected" in payload
    assert "persons_created" in payload


def test_health_services_agree_with_services_endpoint() -> None:
    """Integration test: service flags in /api/health should match
    the configured booleans in /api/services."""
    health = client.get("/api/health").json()
    services = client.get("/api/services").json()

    health_flags = health["services"]
    service_flags = {s["name"]: s["configured"] for s in services}

    assert health_flags == service_flags


def test_tasks_endpoint_has_valid_structure() -> None:
    """Integration test: /api/tasks returns valid TaskPhase objects."""
    response = client.get("/api/tasks")
    assert response.status_code == 200
    phases = response.json()

    assert len(phases) >= 1
    for phase in phases:
        assert "id" in phase
        assert "title" in phase
        assert "timebox" in phase
        assert "tasks" in phase
        assert isinstance(phase["tasks"], list)

        for task in phase["tasks"]:
            assert "id" in task
            assert "title" in task
            assert "area" in task
            assert "status" in task
            assert task["status"] in ("pending", "in_progress", "done")
            assert "acceptance" in task
