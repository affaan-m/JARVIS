"""Webhook capture endpoints for JARVIS.

Provides two routes:
  POST /api/capture/webhook — accepts base64-encoded image payloads
  POST /api/capture/url    — accepts an image URL, downloads, and feeds the pipeline
"""
from __future__ import annotations

from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from pipeline import CapturePipeline

router = APIRouter(prefix="/api/capture", tags=["capture"])

# Injected at startup from main.py
_pipeline: CapturePipeline | None = None


def set_pipeline(pipeline: CapturePipeline) -> None:
    global _pipeline  # noqa: PLW0603
    _pipeline = pipeline


def _get_pipeline() -> CapturePipeline:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")
    return _pipeline


# ---------- request / response models ----------

class WebhookRequest(BaseModel):
    image_base64: str = Field(..., description="Base64-encoded image bytes")
    source: str = Field(default="webhook", description="Source identifier")


class UrlRequest(BaseModel):
    url: str = Field(..., description="Public URL of the image to fetch")
    source: str = Field(default="url_import", description="Source identifier")


class CaptureResponse(BaseModel):
    capture_id: str
    status: str
    source: str
    total_frames: int = 0
    faces_detected: int = 0
    persons_created: list[str] = Field(default_factory=list)
    error: str | None = None


# ---------- routes ----------

@router.post("/webhook", response_model=CaptureResponse)
async def capture_webhook(body: WebhookRequest) -> CaptureResponse:
    """Accept a base64-encoded image and run it through the pipeline."""
    import base64

    pipeline = _get_pipeline()
    capture_id = f"cap_{uuid4().hex[:12]}"

    try:
        data = base64.b64decode(body.image_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64: {exc}") from exc

    if not data:
        raise HTTPException(status_code=400, detail="Decoded image is empty")

    logger.info("Webhook capture {} from source={}, {} bytes", capture_id, body.source, len(data))

    result = await pipeline.process(
        capture_id=capture_id,
        data=data,
        content_type="image/jpeg",
        source=body.source,
    )

    return CaptureResponse(
        capture_id=capture_id,
        status="processed" if result.success else "error",
        source=body.source,
        total_frames=result.total_frames,
        faces_detected=result.faces_detected,
        persons_created=list(result.persons_created),
        error=result.error,
    )


@router.post("/url", response_model=CaptureResponse)
async def capture_url(body: UrlRequest) -> CaptureResponse:
    """Download an image from a URL and run it through the pipeline."""
    pipeline = _get_pipeline()
    capture_id = f"cap_{uuid4().hex[:12]}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(body.url)
            resp.raise_for_status()
            data = resp.content
            content_type = resp.headers.get("content-type", "image/jpeg")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Image download failed with status {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Image download failed: {exc}",
        ) from exc

    if not data:
        raise HTTPException(status_code=400, detail="Downloaded image is empty")

    logger.info(
        "URL capture {} from source={}, url={}, {} bytes",
        capture_id, body.source, body.url, len(data),
    )

    result = await pipeline.process(
        capture_id=capture_id,
        data=data,
        content_type=content_type,
        source=body.source,
    )

    return CaptureResponse(
        capture_id=capture_id,
        status="processed" if result.success else "error",
        source=body.source,
        total_frames=result.total_frames,
        faces_detected=result.faces_detected,
        persons_created=list(result.persons_created),
        error=result.error,
    )
