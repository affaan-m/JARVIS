from __future__ import annotations

from typing import Protocol

from identification.models import (
    FaceDetectionRequest,
    FaceDetectionResult,
    FaceSearchRequest,
    FaceSearchResult,
)


class FaceDetector(Protocol):
    """Contract for face detection in images/frames."""

    @property
    def configured(self) -> bool: ...

    async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
        """Detect faces in an image and return bounding boxes + embeddings."""
        ...


class FaceSearcher(Protocol):
    """Contract for reverse face search (PimEyes, PicImageSearch, etc.)."""

    @property
    def configured(self) -> bool: ...

    async def search_face(self, request: FaceSearchRequest) -> FaceSearchResult:
        """Search for a face across the web. Returns matching profiles."""
        ...
