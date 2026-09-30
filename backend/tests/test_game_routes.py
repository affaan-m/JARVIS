from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from game import routes
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_game():
    routes.configure(enabled=False)
    routes.get_engine().reset()
    yield
    routes.configure(enabled=False)
    routes.get_engine().reset()


def _enable(**setup) -> None:
    assert client.post("/api/game/mode", json={"enabled": True}).status_code == 200
    # Tests must not depend on the wall clock, so open the window all day
    body = {"play_window_start": "00:00", "play_window_end": "23:59", **setup}
    assert client.post("/api/game/new", json=body).status_code == 200


def _join(name: str, **kw) -> str:
    resp = client.post("/api/game/join", json={"name": name, **kw})
    assert resp.status_code == 200, resp.text
    return resp.json()["player_id"]


# ── the toggle ──

def test_game_routes_are_closed_while_the_mode_is_off() -> None:
    assert client.post("/api/game/join", json={"name": "Jamal"}).status_code == 404
    assert client.get("/api/game/state").status_code == 404
    assert client.post("/api/game/start").status_code == 404


def test_the_mode_endpoint_itself_stays_reachable_when_off() -> None:
    resp = client.get("/api/game/mode")
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_turning_the_mode_on_opens_the_routes() -> None:
    _enable()
    assert client.get("/api/game/mode").json()["enabled"] is True
    assert client.get("/api/game/state").status_code == 200


def test_turning_the_mode_off_wipes_the_game() -> None:
    _enable()
    _join("Jamal")
    _join("Sam")
    assert len(routes.get_engine().players) == 2

    client.post("/api/game/mode", json={"enabled": False})

    assert routes.get_engine().players == {}
    assert client.get("/api/game/state").status_code == 404


def test_the_normal_capture_route_is_unaffected_by_the_toggle() -> None:
    _enable()
    assert client.get("/api/health").status_code == 200
    services = client.get("/api/services")
    assert services.status_code == 200


# ── playing through the API ──

def test_full_round_needs_the_target_to_confirm() -> None:
    _enable()
    a = _join("Jamal", hints=["ik zit op 3"])
    b = _join("Sam", hints=["ik draag rood"])
    assert client.post("/api/game/start").status_code == 200

    me = client.get("/api/game/state", params={"player_id": a}).json()["me"]
    target_id = me["target_id"]
    assert target_id in (a, b) and target_id != a

    tag = client.post(
        "/api/game/tags", json={"tagger_id": a, "target_id": target_id},
    ).json()
    assert tag["status"] == "pending"

    # The tagger cannot confirm their own claim
    refused = client.post(
        f"/api/game/tags/{tag['tag_id']}/confirm", json={"player_id": a},
    )
    assert refused.status_code == 400

    ok = client.post(
        f"/api/game/tags/{tag['tag_id']}/confirm", json={"player_id": target_id},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "confirmed"


def test_a_pending_tag_shows_up_for_the_target_only() -> None:
    _enable()
    a = _join("Jamal")
    b = _join("Sam")
    client.post("/api/game/start")
    target_id = client.get("/api/game/state", params={"player_id": a}).json()["me"]["target_id"]
    client.post("/api/game/tags", json={"tagger_id": a, "target_id": target_id})

    for_target = client.get("/api/game/state", params={"player_id": target_id}).json()
    for_other = client.get(
        "/api/game/state", params={"player_id": a if target_id == b else b},
    ).json()

    assert len(for_target["pending_tags"]) == 1
    assert for_other["pending_tags"] == []


def test_a_player_can_leave_and_is_gone_from_the_state() -> None:
    _enable()
    a = _join("Jamal")
    _join("Sam")

    assert client.delete(f"/api/game/players/{a}").status_code == 200

    ids = [p["player_id"] for p in client.get("/api/game/state").json()["players"]]
    assert a not in ids


def test_pausing_location_sharing_through_the_api() -> None:
    _enable()
    a = _join("Jamal")
    _join("Sam")
    client.post("/api/game/start")

    client.post(f"/api/game/players/{a}/location", json={"zone": "floor-3", "sharing": True})
    paused = client.post(
        f"/api/game/players/{a}/location", json={"sharing": False},
    ).json()

    assert paused["sharing_location"] is False
    assert client.get(f"/api/game/players/{a}/radar").json()["proximity"] == "unknown"


def test_starting_with_one_player_is_a_clean_error() -> None:
    _enable()
    _join("Jamal")
    resp = client.post("/api/game/start")
    assert resp.status_code == 400
    assert "2 spelers" in resp.json()["detail"]


def test_new_game_applies_the_chosen_rules() -> None:
    _enable()
    resp = client.post("/api/game/new", json={
        "mode": "king",
        "safe_zones": ["toilet", "vergaderruimte"],
        "duration_minutes": 60,
        "play_window_start": "09:00",
        "play_window_end": "17:00",
    })
    assert resp.status_code == 200
    config = resp.json()["config"]
    assert config["mode"] == "king"
    assert config["safe_zones"] == ["toilet", "vergaderruimte"]


def test_feed_and_scoreboard_are_served() -> None:
    _enable()
    a = _join("Jamal")
    b = _join("Sam")
    client.post("/api/game/start")

    item = client.post(
        "/api/game/feed", json={"player_id": a, "photo_id": "ph1", "text": "gespot"},
    ).json()
    client.post(f"/api/game/feed/{item['item_id']}/vote", json={"player_id": b})

    board = client.get("/api/game/scoreboard").json()["scoreboard"]
    assert len(board) == 2
    state = client.get("/api/game/state", params={"player_id": a}).json()
    photo = next(i for i in state["feed"] if i["kind"] == "photo")
    assert photo["votes"] == 1
