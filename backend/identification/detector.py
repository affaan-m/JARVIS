# RESEARCH: Checked mediapipe (Google, 28k stars), facenet-pytorch (4.5k stars), dlib (13k stars)
# DECISION: Using mediapipe FaceDetection — lightweight, real-time, no GPU required
# ALT: facenet-pytorch MTCNN as fallback (heavier, higher accuracy)
from __future__ import annotations

import io

import mediapipe as mp
import numpy as np
from loguru import logger
from PIL import Image

from identification.models import (
    BoundingBox,
    DetectedFace,
    FaceDetectionRequest,
    FaceDetectionResult,
)


class MediaPipeFaceDetector:
    """Face detector using Google MediaPipe.

    Implements the FaceDetector protocol from identification/__init__.py.
    """

    def __init__(self, *, model_selection: int = 1, min_detection_confidence: float = 0.5) -> None:
        self._model_selection = model_selection
        self._min_confidence = min_detection_confidence
        self._configured = True

    @property
    def configured(self) -> bool:
        return self._configured

    async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
        """Detect faces in an image using MediaPipe."""
        try:
            img = Image.open(io.BytesIO(request.image_data)).convert("RGB")
            img_array = np.array(img)
            height, width = img_array.shape[:2]
        except Exception as exc:
            logger.error("Failed to decode image for face detection: {}", exc)
            return FaceDetectionResult(success=False, error=f"Image decode failed: {exc}")

        try:
            with mp.solutions.face_detection.FaceDetection(
                model_selection=self._model_selection,
                min_detection_confidence=self._min_confidence,
            ) as face_detection:
                results = face_detection.process(img_array)
        except Exception as exc:
            logger.error("MediaPipe face detection failed: {}", exc)
            return FaceDetectionResult(
                frame_width=width,
                frame_height=height,
                success=False,
                error=f"Detection failed: {exc}",
            )

        faces: list[DetectedFace] = []
        if results.detections:
            for detection in results.detections[: request.max_faces]:
                score = detection.score[0] if detection.score else 0.0
                if score < request.min_confidence:
                    continue

                bbox_mp = detection.location_data.relative_bounding_box
                bbox = BoundingBox(
                    x=max(0.0, min(1.0, bbox_mp.xmin)),
                    y=max(0.0, min(1.0, bbox_mp.ymin)),
                    width=max(0.0, min(1.0, bbox_mp.width)),
                    height=max(0.0, min(1.0, bbox_mp.height)),
                )

                faces.append(DetectedFace(
                    bbox=bbox,
                    confidence=score,
                    embedding=[],  # Embeddings filled by the embedder stage
                ))

        logger.info("Detected {} face(s) in {}x{} frame", len(faces), width, height)
        return FaceDetectionResult(
            faces=faces,
            frame_width=width,
            frame_height=height,
            success=True,
        )
