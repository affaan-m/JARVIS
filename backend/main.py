from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from agents.browser_use_client import BrowserUseClient, BrowserUseError
from agents.orchestrator import ResearchOrchestrator
from capture.frame_handler import FrameHandler
from capture.service import CaptureService
from capture.telegram_bot import TelegramCaptureBot, create_telegram_bot
from capture.webhook import router as webhook_router
from capture.webhook import set_pipeline
from config import get_settings
from db.convex_client import ConvexGateway
from db.memory_gateway import InMemoryDatabaseGateway
from enrichment.exa_client import ExaEnrichmentClient
from identification.detector import MediaPipeFaceDetector
from identification.embedder import ArcFaceEmbedder
from memory.supermemory_client import SuperMemoryClient
from observability.laminar import initialize_laminar
from pipeline import CapturePipeline
from schemas import (
    AgentInfo,
    AgentStartRequest,
    AgentStartResponse,
    FrameProcessedResponse,
    FrameSubmission,
    HealthResponse,
    IdentifyRequest,
    IdentifyResponse,
    ServiceStatus,
    SessionStatusResponse,
    TaskInfo,
    TaskPhase,
    TaskStep,
)
from synthesis.anthropic_engine import AnthropicSynthesisEngine
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
synthesis_engine = AnthropicSynthesisEngine(settings) if settings.anthropic_api_key else None
synthesis_fallback = GeminiSynthesisEngine(settings) if settings.gemini_api_key else None

# SuperMemory for person dossier caching (None when API key missing)
supermemory_client = SuperMemoryClient(settings.supermemory_api_key) if settings.supermemory_api_key else None

pipeline = CapturePipeline(
    detector=detector,
    embedder=embedder,
    db=db_gateway,
    exa_client=exa_client,
    orchestrator=orchestrator,
    synthesis_engine=synthesis_engine,
    synthesis_fallback=synthesis_fallback,
    supermemory=supermemory_client,
)

capture_service = CaptureService(pipeline=pipeline)
frame_handler = FrameHandler()
bu_client = BrowserUseClient(settings)
upload_file = File(...)

# Wire webhook router to the same pipeline
set_pipeline(pipeline)

# Telegram bot (None when unconfigured)
telegram_bot: TelegramCaptureBot | None = create_telegram_bot(
    settings.telegram_bot_token, pipeline,
)

# Task prompts keyed by source type
SOURCE_CONFIGS: dict[str, dict[str, str]] = {
    "linkedin": {
        "tp": "SOCIAL",
        "nm": "LinkedIn Profile",
        "prompt": (
            "Search LinkedIn for '{name}'. Navigate to their profile. "
            "Extract: current role, company, work history (last 3 positions), "
            "education, notable connections, and recent posts."
        ),
        "start_url": "https://linkedin.com",
    },
    "twitter": {
        "tp": "SOCIAL",
        "nm": "Twitter/X Activity",
        "prompt": (
            "Search Twitter/X for '{name}'. Find their profile. "
            "Extract: bio, follower count, recent tweets (last 10), "
            "and accounts they interact with most."
        ),
        "start_url": "https://twitter.com",
    },
    "google": {
        "tp": "MEDIA",
        "nm": "Google Search Results",
        "prompt": (
            "Search Google for '{name}'. Look for news articles, "
            "company mentions, and public records. Extract all relevant "
            "results with their URLs and summaries."
        ),
        "start_url": "https://google.com",
    },
    "crunchbase": {
        "tp": "CORPORATE",
        "nm": "Crunchbase Profile",
        "prompt": (
            "Search Crunchbase for '{name}'. Find their profile or companies. "
            "Extract: role, companies, funding rounds, investors, and exits."
        ),
        "start_url": "https://crunchbase.com",
    },
}

# Cache share URLs so we only call make_session_public once
_share_url_cache: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "SPECTER started — det={} emb={} db={} exa={} orch={} synth={} (primary) synth_fallback={} supermemory={}",
        detector.__class__.__name__,
        embedder.__class__.__name__,
        db_gateway.__class__.__name__,
        exa_client is not None,
        orchestrator is not None,
        synthesis_engine.__class__.__name__ if synthesis_engine else None,
        synthesis_fallback.__class__.__name__ if synthesis_fallback else None,
        supermemory_client is not None,
    )
    if telegram_bot:
        await telegram_bot.start()
    yield
    if telegram_bot:
        await telegram_bot.stop()
    if supermemory_client:
        await supermemory_client.close()
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
        "anthropic": "Primary synthesis model (Claude)",
        "gemini": "Fallback vision and synthesis model when Anthropic unavailable",
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


@app.post("/api/capture/frame", response_model=FrameProcessedResponse)
async def capture_frame(submission: FrameSubmission) -> FrameProcessedResponse:
    result = await frame_handler.process_frame(
        frame_b64=submission.frame,
        timestamp=submission.timestamp,
        source=submission.source,
    )
    return FrameProcessedResponse(**result)


@app.post("/api/capture/identify", response_model=IdentifyResponse)
async def identify(body: IdentifyRequest) -> IdentifyResponse:
    """Identify a person by name + image URL. Downloads the image, runs the full pipeline."""
    capture_id = f"identify_{uuid4().hex[:12]}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(body.image_url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download image: HTTP {exc.response.status_code}",
            ) from exc
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download image: {exc}",
            ) from exc

    content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]
    image_data = resp.content

    result = await pipeline.process(
        capture_id=capture_id,
        data=image_data,
        content_type=content_type,
        source="api_identify",
        person_name=body.name,
    )

    return IdentifyResponse(
        capture_id=result.capture_id,
        total_frames=result.total_frames,
        faces_detected=result.faces_detected,
        persons_created=list(result.persons_created),
        persons_enriched=result.persons_enriched,
        success=result.success,
        error=result.error,
    )


@app.get("/api/person/{person_id}")
async def get_person(person_id: str):
    """Retrieve stored person data + dossier by ID."""
    person = await db_gateway.get_person(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Person {person_id} not found")
    return person


# --- Browser Use agent research ---


@app.post("/api/agents/research", response_model=AgentStartResponse)
async def start_research(req: AgentStartRequest) -> AgentStartResponse:
    """Spawn Browser Use sessions/tasks per source type. Returns immediately."""
    agents: list[AgentInfo] = []
    for source_key in req.sources:
        cfg = SOURCE_CONFIGS.get(source_key)
        if not cfg:
            logger.warning("Unknown source type: {}", source_key)
            continue
        try:
            session = await bu_client.create_session(start_url=cfg["start_url"])
            session_id = session["id"]
            prompt = cfg["prompt"].replace("{name}", req.person_name)
            task = await bu_client.create_task(
                session_id=session_id,
                task=prompt,
                start_url=cfg["start_url"],
            )
            agents.append(AgentInfo(
                source_tp=cfg["tp"],
                source_nm=cfg["nm"],
                session_id=session_id,
                task_id=task["id"],
                live_url=session.get("liveUrl"),
                session_status="running",
            ))
        except BrowserUseError as e:
            logger.error("Failed to create agent for {}: {}", source_key, e)
            continue
        except Exception as e:
            logger.error("Unexpected error creating agent for {}: {}", source_key, e)
            continue
    return AgentStartResponse(person_id=req.person_id, agents=agents)


def _map_bu_status(bu_status: str | None) -> str:
    """Map Browser Use status strings to our status enum."""
    mapping = {
        "active": "running",
        "created": "pending",
        "started": "running",
        "running": "running",
        "idle": "running",
        "finished": "completed",
        "stopped": "completed",
        "timed_out": "failed",
        "error": "failed",
    }
    return mapping.get(bu_status or "", "pending")


@app.get("/api/agents/sessions/{session_id}", response_model=SessionStatusResponse)
async def get_session_status(session_id: str) -> SessionStatusResponse:
    """Proxy Browser Use session + task status for frontend polling."""
    try:
        session = await bu_client.get_session(session_id)
    except BrowserUseError as e:
        logger.error("Failed to get session {}: {}", session_id, e)
        return SessionStatusResponse(session_id=session_id, session_status="failed")

    session_status = _map_bu_status(session.get("status"))
    live_url = session.get("liveUrl")
    share_url = session.get("publicShareUrl") or _share_url_cache.get(session_id)

    # On first completed fetch, create public share for replay
    if session_status == "completed" and not share_url and session_id not in _share_url_cache:
        try:
            share_data = await bu_client.make_session_public(session_id)
            share_url = share_data.get("shareUrl")
            if share_url:
                _share_url_cache[session_id] = share_url
        except BrowserUseError:
            logger.warning("Could not create public share for session {}", session_id)

    # Get task details if available
    task_info = None
    tasks_list = session.get("tasks", [])
    if tasks_list:
        task_id = tasks_list[0].get("id") if isinstance(tasks_list[0], dict) else tasks_list[0]
        try:
            task_data = await bu_client.get_task(task_id)
            raw_steps = task_data.get("steps", [])
            steps = [
                TaskStep(
                    number=s.get("number", i + 1),
                    url=s.get("url"),
                    screenshot_url=s.get("screenshotUrl"),
                    next_goal=s.get("nextGoal"),
                )
                for i, s in enumerate(raw_steps)
            ]
            task_info = TaskInfo(
                task_id=task_id,
                status=task_data.get("status"),
                steps=steps,
                output=task_data.get("output"),
            )
        except BrowserUseError:
            logger.warning("Could not get task {} for session {}", task_id, session_id)

    return SessionStatusResponse(
        session_id=session_id,
        session_status=session_status,
        live_url=live_url,
        share_url=share_url,
        task=task_info,
    )
