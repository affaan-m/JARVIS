from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_endpoint_returns_ok() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "services" in payload


def test_tasks_endpoint_returns_seeded_phases() -> None:
    response = client.get("/api/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert payload[0]["id"] == "foundation"
