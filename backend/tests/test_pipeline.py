from __future__ import annotations

import io

import pytest
from PIL import Image

from capture.frame_extractor import extract_frames
from db.memory_gateway import InMemoryDatabaseGateway
from identification.embedder import ArcFaceEmbedder
from identification.models import (
    BoundingBox,
    DetectedFace,
    FaceDetectionRequest,
    FaceDetectionResult,
)
from pipeline import CapturePipeline


def _make_jpeg(width: int = 100, height: int = 100) -> bytes:
    """Create a minimal valid JPEG image."""
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class FakeDetector:
    """Test double that returns a fixed set of faces."""

    def __init__(self, faces: list[DetectedFace] | None = None) -> None:
        self._faces = faces or []

    @property
    def configured(self) -> bool:
        return True

    async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
        return FaceDetectionResult(
            faces=self._faces,
            frame_width=100,
            frame_height=100,
            success=True,
        )


class FailingDetector:
    """Test double that always fails detection."""

    @property
    def configured(self) -> bool:
        return True

    async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
        return FaceDetectionResult(success=False, error="Simulated failure")


# --- Frame Extractor Tests ---


def test_extract_frames_image_jpeg() -> None:
    jpeg_bytes = _make_jpeg()
    frames = extract_frames(jpeg_bytes, "image/jpeg")
    assert len(frames) == 1
    assert len(frames[0]) > 0


def test_extract_frames_image_png() -> None:
    img = Image.new("RGB", (50, 50), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    frames = extract_frames(buf.getvalue(), "image/png")
    assert len(frames) == 1


def test_extract_frames_unknown_type_treated_as_image() -> None:
    jpeg_bytes = _make_jpeg()
    frames = extract_frames(jpeg_bytes, "application/octet-stream")
    assert len(frames) == 1


def test_extract_frames_video_without_ffmpeg() -> None:
    """Video extraction with invalid data returns empty (ffmpeg fails gracefully)."""
    frames = extract_frames(b"not a video", "video/mp4")
    assert isinstance(frames, list)


# --- Embedder Tests ---


def test_embedder_produces_512_dim_vector() -> None:
    embedder = ArcFaceEmbedder()
    face = DetectedFace(
        bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4),
        confidence=0.95,
    )
    embedding = embedder.embed(face, b"fake image")
    assert len(embedding) == 512
    assert all(isinstance(v, float) for v in embedding)


def test_embedder_deterministic() -> None:
    embedder = ArcFaceEmbedder()
    face = DetectedFace(
        bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4),
        confidence=0.95,
    )
    e1 = embedder.embed(face, b"same image data")
    e2 = embedder.embed(face, b"same image data")
    assert e1 == e2


def test_embedder_different_faces_different_embeddings() -> None:
    embedder = ArcFaceEmbedder()
    face_a = DetectedFace(
        bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4),
        confidence=0.95,
    )
    face_b = DetectedFace(
        bbox=BoundingBox(x=0.5, y=0.6, width=0.2, height=0.2),
        confidence=0.90,
    )
    e1 = embedder.embed(face_a, b"image")
    e2 = embedder.embed(face_b, b"image")
    assert e1 != e2


# --- In-Memory DB Tests ---


@pytest.mark.asyncio
async def test_memory_gateway_store_and_get_person() -> None:
    gw = InMemoryDatabaseGateway()
    await gw.store_person("p1", {"name": "Alice"})
    result = await gw.get_person("p1")
    assert result is not None
    assert result["name"] == "Alice"


@pytest.mark.asyncio
async def test_memory_gateway_get_missing_person() -> None:
    gw = InMemoryDatabaseGateway()
    assert await gw.get_person("nonexistent") is None


@pytest.mark.asyncio
async def test_memory_gateway_update_person() -> None:
    gw = InMemoryDatabaseGateway()
    await gw.store_person("p1", {"name": "Alice"})
    await gw.update_person("p1", {"occupation": "Engineer"})
    result = await gw.get_person("p1")
    assert result is not None
    assert result["name"] == "Alice"
    assert result["occupation"] == "Engineer"


# --- Pipeline Integration Tests ---


@pytest.mark.asyncio
async def test_pipeline_no_faces_detected() -> None:
    """Pipeline completes successfully even when no faces are found."""
    detector = FakeDetector(faces=[])
    embedder = ArcFaceEmbedder()
    db = InMemoryDatabaseGateway()
    pipeline = CapturePipeline(detector=detector, embedder=embedder, db=db)

    result = await pipeline.process(
        capture_id="cap_test001",
        data=_make_jpeg(),
        content_type="image/jpeg",
    )

    assert result.success is True
    assert result.total_frames == 1
    assert result.faces_detected == 0
    assert result.persons_created == []


@pytest.mark.asyncio
async def test_pipeline_one_face_creates_person() -> None:
    """Pipeline detects one face and creates a person record."""
    face = DetectedFace(
        bbox=BoundingBox(x=0.1, y=0.2, width=0.3, height=0.4),
        confidence=0.95,
    )
    detector = FakeDetector(faces=[face])
    embedder = ArcFaceEmbedder()
    db = InMemoryDatabaseGateway()
    pipeline = CapturePipeline(detector=detector, embedder=embedder, db=db)

    result = await pipeline.process(
        capture_id="cap_test002",
        data=_make_jpeg(),
        content_type="image/jpeg",
    )

    assert result.success is True
    assert result.total_frames == 1
    assert result.faces_detected == 1
    assert len(result.persons_created) == 1
    assert result.persons_created[0].startswith("person_")

    # Verify person is in the database
    person = await db.get_person(result.persons_created[0])
    assert person is not None
    assert person["capture_id"] == "cap_test002"
    assert person["confidence"] == 0.95
    assert len(person["embedding"]) == 512


@pytest.mark.asyncio
async def test_pipeline_multiple_faces() -> None:
    """Pipeline handles multiple faces in a single frame."""
    faces = [
        DetectedFace(
            bbox=BoundingBox(x=0.1, y=0.1, width=0.2, height=0.2),
            confidence=0.9,
        ),
        DetectedFace(
            bbox=BoundingBox(x=0.5, y=0.5, width=0.2, height=0.2),
            confidence=0.85,
        ),
    ]
    detector = FakeDetector(faces=faces)
    embedder = ArcFaceEmbedder()
    db = InMemoryDatabaseGateway()
    pipeline = CapturePipeline(detector=detector, embedder=embedder, db=db)

    result = await pipeline.process(
        capture_id="cap_test003",
        data=_make_jpeg(),
        content_type="image/jpeg",
    )

    assert result.success is True
    assert result.faces_detected == 2
    assert len(result.persons_created) == 2


@pytest.mark.asyncio
async def test_pipeline_detection_failure_is_graceful() -> None:
    """Pipeline handles detection failure without crashing."""
    detector = FailingDetector()
    embedder = ArcFaceEmbedder()
    db = InMemoryDatabaseGateway()
    pipeline = CapturePipeline(detector=detector, embedder=embedder, db=db)

    result = await pipeline.process(
        capture_id="cap_test004",
        data=_make_jpeg(),
        content_type="image/jpeg",
    )

    assert result.success is True
    assert result.faces_detected == 0
    assert result.persons_created == []


@pytest.mark.asyncio
async def test_pipeline_stores_capture_metadata() -> None:
    """Pipeline stores capture metadata in the database."""
    detector = FakeDetector(faces=[])
    embedder = ArcFaceEmbedder()
    db = InMemoryDatabaseGateway()
    pipeline = CapturePipeline(detector=detector, embedder=embedder, db=db)

    await pipeline.process(
        capture_id="cap_meta01",
        data=_make_jpeg(),
        content_type="image/jpeg",
        source="telegram",
    )

    capture = db._captures.get("cap_meta01")
    assert capture is not None
    assert capture["source"] == "telegram"
    assert capture["status"] == "completed"
