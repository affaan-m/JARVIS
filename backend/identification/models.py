from __future__ import annotations

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Face bounding box coordinates (normalized 0-1)."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class DetectedFace(BaseModel):
    """A single detected face with embedding."""

    bbox: BoundingBox
    confidence: float = Field(ge=0.0, le=1.0)
    embedding: list[float] = Field(default_factory=list)


class FaceDetectionRequest(BaseModel):
    """Input for face detection."""

    image_data: bytes
    max_faces: int = Field(default=10, ge=1, le=50)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class FaceDetectionResult(BaseModel):
    """Output from face detection."""

    faces: list[DetectedFace] = Field(default_factory=list)
    frame_width: int = 0
    frame_height: int = 0
    success: bool = True
    error: str | None = None


class FaceSearchRequest(BaseModel):
    """Input for reverse face search."""

    embedding: list[float]
    image_data: bytes | None = None
    search_engines: list[str] = Field(default_factory=lambda: ["pimeyes"])


class FaceSearchMatch(BaseModel):
    """A single match from reverse face search."""

    url: str
    thumbnail_url: str | None = None
    similarity: float = Field(ge=0.0, le=1.0)
    source: str
    person_name: str | None = None


class FaceSearchResult(BaseModel):
    """Output from reverse face search."""

    matches: list[FaceSearchMatch] = Field(default_factory=list)
    success: bool = True
    error: str | None = None
