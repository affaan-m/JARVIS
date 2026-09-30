# RESEARCH: Checked mediapipe (Google, 28k stars), facenet-pytorch (4.5k stars), dlib (13k stars)
# DECISION: Using mediapipe FaceDetection — lightweight, real-time, no GPU required
# NOTE: mediapipe 0.10.x removed mp.solutions; uses Task API (mp.tasks.vision.FaceDetector)
from __future__ import annotations

import asyncio
import io
import threading
from pathlib import Path

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

_MODEL_PATH = Path(__file__).parent / "models" / "blaze_face_short_range.tflite"

BaseOptions = mp.tasks.BaseOptions
FaceDetector = mp.tasks.vision.FaceDetector
FaceDetectorOptions = mp.tasks.vision.FaceDetectorOptions


class MediaPipeFaceDetector:
    """Face detector using Google MediaPipe Task API (0.10.x+).

    Implements the FaceDetector protocol from identification/__init__.py.
    """

    def __init__(self, *, min_detection_confidence: float = 0.5) -> None:
        self._min_confidence = min_detection_confidence
        self._model_path = str(_MODEL_PATH)
        self._configured = _MODEL_PATH.exists()
        # The MediaPipe detector is expensive to build (model load + XNNPACK init),
        # so it is created once and reused. It is not thread-safe, hence the lock.
        self._detector = None
        self._detector_lock = threading.Lock()
        if not self._configured:
            logger.warning("MediaPipe model not found at {}", _MODEL_PATH)

    def _detect_sync(self, img_array: np.ndarray):
        """Blocking MediaPipe detection — always called off the event loop."""
        with self._detector_lock:
            if self._detector is None:
                options = FaceDetectorOptions(
                    base_options=BaseOptions(model_asset_path=self._model_path),
                    min_detection_confidence=self._min_confidence,
                )
                self._detector = FaceDetector.create_from_options(options)
                logger.info("MediaPipe FaceDetector loaded (reused for later frames)")
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_array)
            return self._detector.detect(mp_image)

    @property
    def configured(self) -> bool:
        return self._configured

    async def detect_faces(self, request: FaceDetectionRequest) -> FaceDetectionResult:
        """Detect faces in an image using MediaPipe Task API."""
        def _decode() -> np.ndarray:
            return np.array(Image.open(io.BytesIO(request.image_data)).convert("RGB"))

        try:
            img_array = await asyncio.to_thread(_decode)
            height, width = img_array.shape[:2]
        except Exception as exc:
            logger.error("Failed to decode image for face detection: {}", exc)
            return FaceDetectionResult(success=False, error=f"Image decode failed: {exc}")

        if not self._configured:
            return FaceDetectionResult(
                frame_width=width,
                frame_height=height,
                success=False,
                error="Face detection model file not found",
            )

        try:
            result = await asyncio.to_thread(self._detect_sync, img_array)
        except Exception as exc:
            logger.error("MediaPipe face detection failed: {}", exc)
            return FaceDetectionResult(
                frame_width=width,
                frame_height=height,
                success=False,
                error=f"Detection failed: {exc}",
            )

        faces: list[DetectedFace] = []
        for detection in result.detections[: request.max_faces]:
            score = detection.categories[0].score if detection.categories else 0.0
            if score < request.min_confidence:
                continue

            bbox_mp = detection.bounding_box
            bbox = BoundingBox(
                x=max(0.0, min(1.0, bbox_mp.origin_x / width)),
                y=max(0.0, min(1.0, bbox_mp.origin_y / height)),
                width=max(0.0, min(1.0, bbox_mp.width / width)),
                height=max(0.0, min(1.0, bbox_mp.height / height)),
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
