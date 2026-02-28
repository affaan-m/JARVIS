from __future__ import annotations

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from capture.service import CaptureService
from config import get_settings
from schemas import HealthResponse, ServiceStatus, TaskPhase
from tasks import TASK_PHASES

settings = get_settings()
capture_service = CaptureService()
upload_file = File(...)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Control plane and service seams for the SPECTER hackathon stack",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        services=settings.service_flags(),
    )


@app.get("/api/services", response_model=list[ServiceStatus])
async def services() -> list[ServiceStatus]:
    descriptions = {
        "convex": "Real-time board subscriptions and mutations",
        "mongodb": "Persistent raw captures and dossiers",
        "exa": "Fast pass research and person lookup",
        "browser_use": "Deep research browser agents",
        "openai": "Transcription and fallback LLM integrations",
        "gemini": "Primary vision and synthesis model",
        "laminar": "Tracing and evaluation telemetry",
        "telegram": "Glasses-side media intake",
        "pimeyes_pool": "Rotating account pool for identification",
    }
    flags = settings.service_flags()
    return [
        ServiceStatus(name=name, configured=configured, notes=descriptions.get(name))
        for name, configured in flags.items()
    ]


@app.get("/api/tasks", response_model=list[TaskPhase])
async def tasks() -> list[TaskPhase]:
    return TASK_PHASES


@app.post("/api/capture")
async def capture(file: UploadFile = upload_file, source: str = "manual_upload"):
    return await capture_service.enqueue_upload(file=file, source=source)
