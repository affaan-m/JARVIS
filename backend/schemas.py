from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    services: dict[str, bool]


class CaptureQueuedResponse(BaseModel):
    capture_id: str
    filename: str
    content_type: str
    status: Literal["queued"]
    source: str


class ServiceStatus(BaseModel):
    name: str
    configured: bool
    notes: str | None = None


class TaskItem(BaseModel):
    id: str
    title: str
    area: str
    status: Literal["pending", "in_progress", "done"] = "pending"
    acceptance: str
    notes: str | None = None


class TaskPhase(BaseModel):
    id: str
    title: str
    timebox: str
    tasks: list[TaskItem] = Field(default_factory=list)


class IdentifyRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Person's full name")
    image_url: str = Field(..., min_length=1, description="URL of a photo of the person")


class IdentifyResponse(BaseModel):
    capture_id: str
    total_frames: int = 0
    faces_detected: int = 0
    persons_created: list[str] = Field(default_factory=list)
    persons_enriched: int = 0
    success: bool = True
    error: str | None = None
