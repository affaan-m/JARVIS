from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from capture.service import CaptureService
from config import get_settings
from db.memory_gateway import InMemoryDatabaseGateway
from identification.detector import MediaPipeFaceDetector
from identification.embedder import ArcFaceEmbedder
from pipeline import CapturePipeline
from schemas import HealthResponse, ServiceStatus, TaskPhase
from tasks import TASK_PHASES

settings = get_settings()

# Build pipeline components
detector = MediaPipeFaceDetector()
embedder = ArcFaceEmbedder()
db_gateway = InMemoryDatabaseGateway()
pipeline = CapturePipeline(detector=detector, embedder=embedder, db=db_gateway)

capture_service = CaptureService(pipeline=pipeline)
upload_file = File(...)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("SPECTER pipeline started — detector={} embedder={} db=in-memory",
                detector.__class__.__name__, embedder.__class__.__name__)
    yield
    logger.info("SPECTER shutting down")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    summary="Control plane and service seams for the SPECTER hackathon stack",
    lifespan=lifespan,
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
