from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from agents.orchestrator import ResearchOrchestrator
from capture.service import CaptureService
from capture.telegram_bot import TelegramCaptureBot, create_telegram_bot
from capture.webhook import router as webhook_router
from capture.webhook import set_pipeline
from config import get_settings
from db.convex_client import ConvexGateway
from observability.laminar import initialize_laminar
from db.memory_gateway import InMemoryDatabaseGateway
from enrichment.exa_client import ExaEnrichmentClient
from identification.detector import MediaPipeFaceDetector
from identification.embedder import ArcFaceEmbedder
from pipeline import CapturePipeline
from schemas import HealthResponse, ServiceStatus, TaskPhase
from synthesis.engine import GeminiSynthesisEngine
from tasks import TASK_PHASES

settings = get_settings()

# Initialize Laminar tracing (no-op if LMNR_PROJECT_API_KEY not set)
initialize_laminar(settings)

# Build pipeline components
detector = MediaPipeFaceDetector()
embedder = ArcFaceEmbedder()

# Database: use Convex when configured, else in-memory
convex_gw = ConvexGateway(settings)
db_gateway = convex_gw if convex_gw.configured else InMemoryDatabaseGateway()

# Enrichment + research + synthesis (None when API keys missing)
exa_client = ExaEnrichmentClient(settings) if settings.exa_api_key else None
orchestrator = ResearchOrchestrator(settings) if settings.browser_use_api_key else None
synthesis_engine = GeminiSynthesisEngine(settings) if settings.gemini_api_key else None

pipeline = CapturePipeline(
    detector=detector,
    embedder=embedder,
    db=db_gateway,
    exa_client=exa_client,
    orchestrator=orchestrator,
    synthesis_engine=synthesis_engine,
)

capture_service = CaptureService(pipeline=pipeline)
upload_file = File(...)

# Wire webhook router to the same pipeline
set_pipeline(pipeline)

# Telegram bot (None when unconfigured)
telegram_bot: TelegramCaptureBot | None = create_telegram_bot(
    settings.telegram_bot_token, pipeline,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "SPECTER started — det={} emb={} db={} exa={} orch={} synth={}",
        detector.__class__.__name__,
        embedder.__class__.__name__,
        db_gateway.__class__.__name__,
        exa_client is not None,
        orchestrator is not None,
        synthesis_engine is not None,
    )
    if telegram_bot:
        await telegram_bot.start()
    yield
    if telegram_bot:
        await telegram_bot.stop()
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

app.include_router(webhook_router)


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
async def capture(
    file: UploadFile = upload_file,
    source: str = "manual_upload",
    person_name: str | None = None,
):
    return await capture_service.enqueue_upload(
        file=file, source=source, person_name=person_name,
    )
