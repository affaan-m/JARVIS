from __future__ import annotations

from uuid import uuid4

from fastapi import UploadFile
from loguru import logger

from pipeline import CapturePipeline, PipelineResult
from schemas import CaptureQueuedResponse


class CaptureService:
    """Process incoming media through the face detection pipeline."""

    def __init__(self, pipeline: CapturePipeline | None = None) -> None:
        self._pipeline = pipeline

    @property
    def pipeline(self) -> CapturePipeline | None:
        return self._pipeline

    @pipeline.setter
    def pipeline(self, value: CapturePipeline) -> None:
        self._pipeline = value

    async def enqueue_upload(
        self,
        file: UploadFile,
        source: str = "manual_upload",
    ) -> CaptureQueuedResponse | dict:
        capture_id = f"cap_{uuid4().hex[:12]}"
        filename = file.filename or "upload.bin"
        content_type = file.content_type or "application/octet-stream"

        if self._pipeline is None:
            logger.warning("No pipeline configured, returning queued response only")
            return CaptureQueuedResponse(
                capture_id=capture_id,
                filename=filename,
                content_type=content_type,
                status="queued",
                source=source,
            )

        data = await file.read()
        result: PipelineResult = await self._pipeline.process(
            capture_id=capture_id,
            data=data,
            content_type=content_type,
            source=source,
        )

        return {
            "capture_id": capture_id,
            "filename": filename,
            "content_type": content_type,
            "status": "processed" if result.success else "error",
            "source": source,
            "total_frames": result.total_frames,
            "faces_detected": result.faces_detected,
            "persons_created": result.persons_created,
            "error": result.error,
        }
