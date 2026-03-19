from __future__ import annotations

import asyncio
import base64
from io import BytesIO
from uuid import uuid4

from loguru import logger
from PIL import Image

from identification.detector import MediaPipeFaceDetector
from identification.embedder import ArcFaceEmbedder
from identification.human_detector import HumanDetector
from identification.models import FaceDetectionRequest, FaceSearchRequest
from identification.search_manager import FaceSearchManager


class Identification:
    """Tracks the state of a single face identification attempt."""

    __slots__ = ("track_id", "status", "name", "person_id", "error")

    def __init__(self, track_id: int) -> None:
        self.track_id = track_id
        self.status: str = "identifying"  # identifying | identified | failed
        self.name: str | None = None
        self.person_id: str | None = None
        self.error: str | None = None

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "status": self.status,
            "name": self.name,
            "person_id": self.person_id,
        }


class FrameHandler:
    """Process incoming stream frames through the full detection → identification pipeline.

    Flow per new face:
      YOLO person detect → crop → MediaPipe face detect → ArcFace embed
      → PimEyes/reverse search → name resolution
    """

    def __init__(
        self,
        face_detector: MediaPipeFaceDetector | None = None,
        embedder: ArcFaceEmbedder | None = None,
        face_searcher: FaceSearchManager | None = None,
    ):
        self.detector = HumanDetector()
        self._face_detector = face_detector
        self._embedder = embedder
        self._face_searcher = face_searcher
        self._seen_tracks: set[int] = set()
        self._identifications: dict[int, Identification] = {}
        # Track IDs that already had identification spawned (prevent double-spawn)
        self._spawned: set[int] = set()
        # Global lock: only one PimEyes search at a time
        self._search_in_progress = False
        logger.info(
            "FrameHandler initialized face_detect={} embed={} search={}",
            face_detector is not None,
            embedder is not None,
            face_searcher is not None,
        )

    async def process_frame(
        self,
        frame_b64: str,
        timestamp: int,
        source: str = "glasses_stream",
        target: bool = False,
    ) -> dict:
        capture_id = f"cap_{uuid4().hex[:12]}"

        # Step 1: Detect humans (YOLO)
        result = self.detector.detect_from_base64(frame_b64)
        detections = result["detections"]

        # Step 2: Track new persons (for detection count only)
        new_detections = []
        for det in detections:
            tid = det.get("track_id")
            if tid is not None and tid not in self._seen_tracks:
                self._seen_tracks.add(tid)
                new_detections.append(det)

        # Step 3: Only spawn face identification when user explicitly targets
        # Regular polling frames just do YOLO detection — no PimEyes spend
        if target and detections and not self._search_in_progress:
            # Use ALL detections (not just new) since user is targeting NOW
            crops = self.detector.crop_persons(frame_b64, detections)
            logger.info("TARGET mode: {} person(s) detected, {} crop(s)", len(detections), len(crops))  # noqa: E501

            if crops:
                # Pick the largest crop (most prominent person in view)
                best_idx = max(range(len(crops)), key=lambda i: len(crops[i]))
                crop_b64 = crops[best_idx]
                det = detections[best_idx]
                tid = det.get("track_id", -1)

                self._spawned.add(tid)
                ident = Identification(tid)
                self._identifications[tid] = ident
                self._search_in_progress = True
                logger.info("TARGET: spawning identification for track_id={}", tid)
                asyncio.create_task(self._identify_face(ident, crop_b64, frame_b64))
        elif target and self._search_in_progress:
            logger.info("TARGET: search already in progress, wait for current to finish")
        elif target and not detections:
            logger.info("TARGET: no persons detected in frame")

        # Collect completed/pending identifications for frontend
        identifications = [
            ident.to_dict() for ident in self._identifications.values()
        ]

        return {
            "capture_id": capture_id,
            "detections": detections,
            "new_persons": len(new_detections),
            "identifications": identifications,
            "timestamp": timestamp,
            "source": source,
        }

    @staticmethod
    def _upscale_for_pimeyes(image_bytes: bytes, min_dim: int = 480) -> bytes:
        """Upscale small crops so PimEyes can detect faces.

        WebRTC streams from the glasses are often ~186x336. YOLO crops can be
        as small as 35x108. PimEyes needs decent resolution to detect faces.
        Upscale using LANCZOS to at least min_dim on the shortest side.
        """
        try:
            img = Image.open(BytesIO(image_bytes))
            w, h = img.size
            short_side = min(w, h)
            if short_side < min_dim:
                scale = min_dim / short_side
                new_w, new_h = int(w * scale), int(h * scale)
                img = img.resize((new_w, new_h), Image.LANCZOS)
                logger.info("Upscaled crop {}x{} → {}x{} for PimEyes", w, h, new_w, new_h)
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=92)
                return buf.getvalue()
            logger.info("Crop {}x{} already large enough for PimEyes", w, h)
        except Exception as exc:
            logger.debug("Upscale failed: {}", exc)
        return image_bytes

    async def _identify_face(
        self, ident: Identification, crop_b64: str, frame_b64: str,
    ) -> None:
        """Background task: face detect → embed → search → name resolution.

        Sends an upscaled crop to PimEyes and the original crop for
        local MediaPipe + ArcFace embedding.
        """
        tid = ident.track_id
        logger.info("Starting face identification for track_id={}", tid)

        if not self._face_detector or not self._embedder or not self._face_searcher:
            logger.warning("Face pipeline not fully configured, skipping identification")
            ident.status = "failed"
            ident.error = "Face pipeline not configured"
            return

        try:
            # Decode crop to raw bytes
            crop_bytes = base64.b64decode(crop_b64)

            # Step 1: MediaPipe face detection on the crop
            face_result = await self._face_detector.detect_faces(
                FaceDetectionRequest(image_data=crop_bytes)
            )

            embedding = None
            if face_result.success and face_result.faces:
                face = face_result.faces[0]
                logger.info("Face detected in crop for track_id={} conf={:.2f}", tid, face.confidence)  # noqa: E501
                # Step 2: ArcFace embedding
                embedding = self._embedder.embed(face, crop_bytes)
                logger.info("Embedding generated for track_id={} dim={}", tid, len(embedding))
            else:
                logger.info("No face in crop for track_id={}, still sending crop to PimEyes", tid)

            # Step 3: Try the upscaled crop first; if PimEyes can't detect
            # a face in it, fall back to the full frame (higher resolution,
            # more context for PimEyes' face detector).
            pimeyes_image = self._upscale_for_pimeyes(crop_bytes)

            # If crop is very small (<150px shortest side), prefer full frame
            from io import BytesIO as _BytesIO

            from PIL import Image as _PILImage
            try:
                _tmp = _PILImage.open(_BytesIO(crop_bytes))
                short_side = min(_tmp.size)
                if short_side < 150:
                    logger.info(
                        "Crop too small ({}px) — using full frame for PimEyes",
                        short_side,
                    )
                    full_frame_bytes = base64.b64decode(frame_b64)
                    pimeyes_image = self._upscale_for_pimeyes(full_frame_bytes)
            except Exception:
                pass  # Stick with crop

            # Step 4: PimEyes / reverse image search
            search_result = await self._face_searcher.search_face(
                FaceSearchRequest(
                    embedding=embedding,
                    image_data=pimeyes_image,
                )
            )

            if not search_result.success or not search_result.matches:
                logger.info("No face search matches for track_id={}", tid)
                ident.status = "failed"
                ident.error = "No matches found"
                return

            # Step 4: Name resolution (frequency analysis across matches)
            name = self._face_searcher.best_name_from_results(search_result)
            if not name:
                logger.info("Matches found but no name extracted for track_id={}", tid)
                ident.status = "failed"
                ident.error = "Matches found but no name"
                return

            logger.info("Face identified: track_id={} → name={}", tid, name)
            ident.status = "identified"
            ident.name = name

        except Exception as exc:
            logger.error("Face identification failed for track_id={}: {}", tid, exc)
            ident.status = "failed"
            ident.error = str(exc)
        finally:
            self._search_in_progress = False
            logger.info("Search lock released for track_id={}", tid)
