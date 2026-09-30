from __future__ import annotations

import base64
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from game import routes
from game.photos import KILLCAM_FRAMES, PhotoStore, blur_faces
from identification.models import BoundingBox, DetectedFace, FaceDetectionResult
from main import app

client = TestClient(app)


def _jpeg(size: tuple[int, int] = (200, 200), colour: str = "red") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="JPEG")
    return buffer.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class _Detector:
    """Stand-in face detector returning fixed boxes."""

    def __init__(self, boxes: list[BoundingBox] | None = None, success: bool = True) -> None:
        self._boxes = boxes or []
        self._success = success

    async def detect_faces(self, request) -> FaceDetectionResult:
        return FaceDetectionResult(
            faces=[DetectedFace(bbox=b, confidence=0.9, embedding=[]) for b in self._boxes],
            frame_width=200,
            frame_height=200,
            success=self._success,
            error=None if self._success else "detector down",
        )


@pytest.fixture(autouse=True)
def _fresh():
    routes.configure(enabled=False)
    routes.get_engine().reset()
    routes.get_photo_store().clear()
    yield
    routes.configure(enabled=False)
    routes.get_engine().reset()
    routes.get_photo_store().clear()


def _enable(detector=None) -> None:
    routes.configure(enabled=True, detector=detector)
    assert client.post(
        "/api/game/new",
        json={"play_window_start": "00:00", "play_window_end": "23:59"},
    ).status_code == 200


# ── blurring ──


@pytest.mark.asyncio
async def test_faces_are_blurred_and_counted() -> None:
    detector = _Detector([BoundingBox(x=0.2, y=0.2, width=0.3, height=0.3)])
    blurred, count = await blur_faces(_jpeg(), detector)

    assert count == 1
    assert blurred != _jpeg()
    assert Image.open(BytesIO(blurred)).size == (200, 200)


@pytest.mark.asyncio
async def test_every_face_is_blurred_not_just_the_first() -> None:
    boxes = [
        BoundingBox(x=0.05, y=0.05, width=0.2, height=0.2),
        BoundingBox(x=0.6, y=0.6, width=0.2, height=0.2),
    ]
    _, count = await blur_faces(_jpeg(), _Detector(boxes))
    assert count == 2


@pytest.mark.asyncio
async def test_a_failing_detector_blurs_the_whole_photo() -> None:
    """Failing closed: an unblurred photo must never be shared."""
    blurred, count = await blur_faces(_jpeg((120, 90), "blue"), _Detector(success=False))

    assert count == 0
    assert blurred != _jpeg((120, 90), "blue")


@pytest.mark.asyncio
async def test_no_detector_at_all_blurs_the_whole_photo() -> None:
    blurred, count = await blur_faces(_jpeg(), None)
    assert count == 0
    assert blurred


@pytest.mark.asyncio
async def test_large_photos_are_shrunk() -> None:
    blurred, _ = await blur_faces(_jpeg((3000, 2000)), _Detector())
    assert max(Image.open(BytesIO(blurred)).size) <= 1280


@pytest.mark.asyncio
async def test_unreadable_bytes_are_refused() -> None:
    with pytest.raises(ValueError):
        await blur_faces(b"this is not an image", _Detector())


# ── the store ──


def test_store_is_bounded_and_drops_the_oldest() -> None:
    store = PhotoStore(max_photos=3)
    ids = [store.add(f"img{i}".encode()) for i in range(4)]

    assert len(store) == 3
    assert store.get(ids[0]) is None
    assert store.get(ids[3]) == b"img3"


def test_killcam_keeps_only_the_last_frames() -> None:
    store = PhotoStore()
    for i in range(KILLCAM_FRAMES + 3):
        store.push_killcam("p1", f"ph{i}")

    frames = store.take_killcam("p1")
    assert len(frames) == KILLCAM_FRAMES
    assert frames[-1] == f"ph{KILLCAM_FRAMES + 2}"
    # Taking it empties the buffer
    assert store.take_killcam("p1") == []


def test_killcam_buffers_are_per_player() -> None:
    store = PhotoStore()
    store.push_killcam("p1", "a")
    store.push_killcam("p2", "b")

    assert store.take_killcam("p1") == ["a"]
    assert store.take_killcam("p2") == ["b"]


def test_dropping_a_photo_also_drops_it_from_the_killcam() -> None:
    store = PhotoStore(max_photos=2)
    first = store.add(b"one")
    store.push_killcam("p1", first)
    store.add(b"two")
    store.add(b"three")  # evicts `first`

    assert store.take_killcam("p1") == []


# ── the endpoints ──


def test_photo_routes_are_closed_while_game_mode_is_off() -> None:
    assert client.post("/api/game/photos", json={"image": _b64(_jpeg())}).status_code == 404
    assert client.get("/api/game/photos/ph_x").status_code == 404


def test_upload_and_serve_a_photo() -> None:
    _enable(_Detector([BoundingBox(x=0.2, y=0.2, width=0.3, height=0.3)]))

    upload = client.post("/api/game/photos", json={"image": _b64(_jpeg())})
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body["faces_blurred"] == 1

    served = client.get(f"/api/game/photos/{body['photo_id']}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert Image.open(BytesIO(served.content)).size == (200, 200)


def test_data_url_prefix_is_accepted() -> None:
    _enable(_Detector())
    resp = client.post(
        "/api/game/photos",
        json={"image": f"data:image/jpeg;base64,{_b64(_jpeg())}"},
    )
    assert resp.status_code == 200


def test_rubbish_upload_is_a_clean_error() -> None:
    _enable(_Detector())
    assert client.post("/api/game/photos", json={"image": "not base64!!"}).status_code == 400
    assert client.post("/api/game/photos", json={"image": ""}).status_code == 400


def test_unknown_photo_is_a_404() -> None:
    _enable(_Detector())
    assert client.get("/api/game/photos/ph_nope").status_code == 404


def test_killcam_frames_land_on_the_confirmed_tag() -> None:
    _enable(_Detector())
    a = client.post("/api/game/join", json={"name": "Jamal"}).json()["player_id"]
    b = client.post("/api/game/join", json={"name": "Sam"}).json()["player_id"]
    client.post("/api/game/start")
    target_id = client.get("/api/game/state", params={"player_id": a}).json()["me"]["target_id"]
    hunter = a if target_id == b else b

    frames = [
        client.post(
            "/api/game/photos",
            json={"image": _b64(_jpeg()), "player_id": hunter, "killcam": True},
        ).json()["photo_id"]
        for _ in range(3)
    ]

    tag = client.post(
        "/api/game/tags", json={"tagger_id": hunter, "target_id": target_id},
    ).json()
    assert tag["killcam"] == frames

    client.post(f"/api/game/tags/{tag['tag_id']}/confirm", json={"player_id": target_id})
    state = client.get("/api/game/state", params={"player_id": hunter}).json()
    broadcast = next(i for i in state["feed"] if i["kind"] == "tag")
    assert broadcast["meta"]["killcam"] == frames


def test_killcam_can_be_left_off_a_claim() -> None:
    _enable(_Detector())
    a = client.post("/api/game/join", json={"name": "Jamal"}).json()["player_id"]
    b = client.post("/api/game/join", json={"name": "Sam"}).json()["player_id"]
    client.post("/api/game/start")
    target_id = client.get("/api/game/state", params={"player_id": a}).json()["me"]["target_id"]
    hunter = a if target_id == b else b
    client.post(
        "/api/game/photos",
        json={"image": _b64(_jpeg()), "player_id": hunter, "killcam": True},
    )

    tag = client.post(
        "/api/game/tags",
        json={"tagger_id": hunter, "target_id": target_id, "with_killcam": False},
    ).json()

    assert tag["killcam"] == []


def test_switching_game_mode_off_wipes_the_photos() -> None:
    _enable(_Detector())
    photo_id = client.post("/api/game/photos", json={"image": _b64(_jpeg())}).json()["photo_id"]
    assert routes.get_photo_store().get(photo_id) is not None

    client.post("/api/game/mode", json={"enabled": False})

    assert len(routes.get_photo_store()) == 0
