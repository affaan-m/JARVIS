from __future__ import annotations

from uuid import uuid4

from fastapi import UploadFile

from schemas import CaptureQueuedResponse


class CaptureService:
    """Queue incoming media for later frame extraction and identification."""

    async def enqueue_upload(
        self,
        file: UploadFile,
        source: str = "manual_upload",
    ) -> CaptureQueuedResponse:
        return CaptureQueuedResponse(
            capture_id=f"cap_{uuid4().hex[:12]}",
            filename=file.filename or "upload.bin",
            content_type=file.content_type or "application/octet-stream",
            status="queued",
            source=source,
        )
