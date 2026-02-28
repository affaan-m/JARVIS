from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from loguru import logger

from capture.frame_extractor import extract_frames
from db import DatabaseGateway
from identification import FaceDetector
from identification.embedder import ArcFaceEmbedder
from identification.models import FaceDetectionRequest


@dataclass(frozen=True)
class PipelineResult:
    """Result of processing a single capture through the pipeline."""

    capture_id: str
    total_frames: int = 0
    faces_detected: int = 0
    persons_created: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None


class CapturePipeline:
    """Orchestrates: media upload -> frame extraction -> face detection -> embedding -> storage."""

    def __init__(
        self,
        *,
        detector: FaceDetector,
        embedder: ArcFaceEmbedder,
        db: DatabaseGateway,
    ) -> None:
        self._detector = detector
        self._embedder = embedder
        self._db = db

    async def process(
        self,
        capture_id: str,
        data: bytes,
        content_type: str,
        source: str = "manual_upload",
    ) -> PipelineResult:
        """Run the full capture-to-person pipeline.

        1. Extract frames from the uploaded media
        2. Detect faces in each frame
        3. Generate embeddings for each face
        4. Create person records in the database
        """
        logger.info(
            "Pipeline started for capture={} type={} source={}",
            capture_id, content_type, source,
        )

        # Store capture metadata
        await self._db.store_capture(capture_id, {
            "content_type": content_type,
            "source": source,
            "status": "processing",
        })

        # Step 1: Frame extraction
        try:
            frames = extract_frames(data, content_type)
        except Exception as exc:
            logger.error("Frame extraction failed for {}: {}", capture_id, exc)
            return PipelineResult(
                capture_id=capture_id, success=False,
                error=f"Frame extraction failed: {exc}",
            )

        if not frames:
            logger.warning("No frames extracted from capture={}", capture_id)
            return PipelineResult(capture_id=capture_id, total_frames=0, success=True)

        logger.info("Extracted {} frame(s) from capture={}", len(frames), capture_id)

        # Step 2 + 3 + 4: Detect, embed, store for each frame
        total_faces = 0
        persons_created: list[str] = []

        for frame_idx, frame_bytes in enumerate(frames):
            request = FaceDetectionRequest(image_data=frame_bytes)
            detection_result = await self._detector.detect_faces(request)

            if not detection_result.success:
                logger.warning(
                    "Detection failed on frame {} of capture={}: {}",
                    frame_idx, capture_id, detection_result.error,
                )
                continue

            for face in detection_result.faces:
                total_faces += 1

                # Generate embedding
                embedding = self._embedder.embed(face, frame_bytes)

                # Create person record
                person_id = f"person_{uuid4().hex[:12]}"
                await self._db.store_person(person_id, {
                    "capture_id": capture_id,
                    "frame_index": frame_idx,
                    "bbox": face.bbox.model_dump(),
                    "confidence": face.confidence,
                    "embedding": embedding,
                    "status": "detected",
                })
                persons_created.append(person_id)

                logger.info(
                    "Created person={} from capture={} frame={} confidence={:.2f}",
                    person_id, capture_id, frame_idx, face.confidence,
                )

        # Update capture status
        await self._db.store_capture(capture_id, {
            "content_type": content_type,
            "source": source,
            "status": "completed",
            "total_frames": len(frames),
            "faces_detected": total_faces,
            "persons_created": persons_created,
        })

        logger.info(
            "Pipeline complete for capture={}: {} frames, {} faces, {} persons",
            capture_id, len(frames), total_faces, len(persons_created),
        )

        return PipelineResult(
            capture_id=capture_id,
            total_frames=len(frames),
            faces_detected=total_faces,
            persons_created=persons_created,
            success=True,
        )
