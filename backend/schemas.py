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


# --- Stream frame capture & YOLO detection ---


class FrameSubmission(BaseModel):
    frame: str  # base64-encoded JPEG
    timestamp: int  # client-side ms since epoch
    source: str = "glasses_stream"


class Detection(BaseModel):
    bbox: list[float]  # [x1, y1, x2, y2]
    confidence: float
    track_id: int | None = None


class FrameProcessedResponse(BaseModel):
    capture_id: str
    detections: list[Detection]
    new_persons: int
    timestamp: int
    source: str


# --- Browser Use agent research ---


class AgentStartRequest(BaseModel):
    person_id: str
    person_name: str
    sources: list[str] = Field(default_factory=lambda: ["linkedin", "twitter", "google"])


class AgentInfo(BaseModel):
    source_tp: str
    source_nm: str
    session_id: str
    task_id: str
    live_url: str | None = None
    session_status: Literal["pending", "running", "completed", "failed"] = "running"


class AgentStartResponse(BaseModel):
    person_id: str
    agents: list[AgentInfo]


class TaskStep(BaseModel):
    number: int
    url: str | None = None
    screenshot_url: str | None = None
    next_goal: str | None = None


class TaskInfo(BaseModel):
    task_id: str
    status: str | None = None
    steps: list[TaskStep] = Field(default_factory=list)
    output: str | None = None


class SessionStatusResponse(BaseModel):
    session_id: str
    session_status: Literal["pending", "running", "completed", "failed"] = "pending"
    live_url: str | None = None
    share_url: str | None = None
    task: TaskInfo | None = None


# --- Identify endpoint ---


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
