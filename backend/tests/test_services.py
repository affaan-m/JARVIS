from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_services_endpoint_returns_list() -> None:
    response = client.get("/api/services")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) > 0


def test_services_each_item_has_required_fields() -> None:
    response = client.get("/api/services")
    payload = response.json()

    for item in payload:
        assert "name" in item
        assert "configured" in item
        assert isinstance(item["configured"], bool)


def test_services_include_known_service_names() -> None:
    response = client.get("/api/services")
    payload = response.json()
    names = {item["name"] for item in payload}

    expected = {
        "convex", "mongodb", "exa", "browser_use", "openai",
        "gemini", "laminar", "telegram", "hibp", "pimeyes_pool",
    }
    assert names == expected


def test_services_include_notes_descriptions() -> None:
    response = client.get("/api/services")
    payload = response.json()

    notes_by_name = {item["name"]: item.get("notes") for item in payload}
    assert notes_by_name["convex"] is not None
    assert "subscriptions" in notes_by_name["convex"].lower()
    assert notes_by_name["exa"] is not None


def test_services_unconfigured_without_env_vars() -> None:
    """Without env vars set, all services should be unconfigured."""
    response = client.get("/api/services")
    payload = response.json()

    for item in payload:
        assert item["configured"] is False, (
            f"{item['name']} should be unconfigured without env vars"
        )
