from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from agents.browser_use_client import BrowserUseClient, BrowserUseError
from agents.deep_researcher import DeepResearcher
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
from identification.search_manager import FaceSearchManager
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
from sse_starlette.sse import EventSourceResponse
from synthesis.anthropic_engine import AnthropicSynthesisEngine
from synthesis.engine import GeminiSynthesisEngine
from tasks import TASK_PHASES

settings = get_settings()

# Log to file so we can tail from CLI
import sys
logger.add("/tmp/ciri_backend.log", rotation="10 MB", level="DEBUG",
           format="{time:HH:mm:ss.SSS} | {level:<7} | {name}:{function}:{line} | {message}")

# Initialize Laminar tracing (no-op if LMNR_PROJECT_API_KEY not set)
initialize_laminar(settings)

# Build pipeline components
detector = MediaPipeFaceDetector()
embedder = ArcFaceEmbedder()

# Database: use Convex when configured, else in-memory
convex_gw = ConvexGateway(settings)
db_gateway = convex_gw if convex_gw.configured else InMemoryDatabaseGateway()

# Face search: PimEyes (primary) + reverse image search (fallback)
# PimEyes now uses direct API with cookies — no email/password needed
face_searcher = FaceSearchManager(settings)

# Enrichment + research + synthesis (None when API keys missing)
exa_client = ExaEnrichmentClient(settings) if settings.exa_api_key else None
orchestrator = ResearchOrchestrator(settings) if (settings.browser_use_api_key or settings.openai_api_key) else None
synthesis_engine = AnthropicSynthesisEngine(settings) if settings.anthropic_api_key else None
synthesis_fallback = GeminiSynthesisEngine(settings) if settings.gemini_api_key else None

# SuperMemory for person dossier caching (None when API key missing)
supermemory_client = SuperMemoryClient(settings.supermemory_api_key) if settings.supermemory_api_key else None

# DeepResearcher — unified pipeline (replaces per-agent orchestrator)
deep_researcher = DeepResearcher(settings) if settings.browser_use_api_key else None

pipeline = CapturePipeline(
    detector=detector,
    embedder=embedder,
    db=db_gateway,
    face_searcher=face_searcher,
    exa_client=exa_client,
    orchestrator=orchestrator,
    synthesis_engine=synthesis_engine,
    synthesis_fallback=synthesis_fallback,
    supermemory=supermemory_client,
)
# Wire DeepResearcher into pipeline for streaming mode
if deep_researcher:
    pipeline._deep_researcher = deep_researcher

capture_service = CaptureService(pipeline=pipeline)
frame_handler = FrameHandler(
    face_detector=detector,
    embedder=embedder,
    face_searcher=face_searcher,
)
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
        "SPECTER started — det={} emb={} db={} face_search={} exa={} deep_researcher={} synth={} (primary) synth_fallback={} supermemory={}",
        detector.__class__.__name__,
        embedder.__class__.__name__,
        db_gateway.__class__.__name__,
        face_searcher is not None,
        exa_client is not None,
        deep_researcher is not None,
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
        target=submission.target,
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


@app.get("/api/pipeline/status")
async def pipeline_status():
    """Diagnostic: show what the face identification pipeline is doing right now."""
    handler_state = {
        "seen_tracks": list(frame_handler._seen_tracks),
        "spawned_identifications": list(frame_handler._spawned),
        "identifications": {
            tid: {
                "status": ident.status,
                "name": ident.name,
                "person_id": ident.person_id,
                "error": ident.error,
            }
            for tid, ident in frame_handler._identifications.items()
        },
        "face_detector_configured": frame_handler._face_detector is not None,
        "embedder_configured": frame_handler._embedder is not None,
        "face_searcher_configured": frame_handler._face_searcher is not None,
    }
    return {
        "frame_handler": handler_state,
        "services": settings.service_flags(),
        "deep_researcher": deep_researcher is not None,
        "synthesis_engine": synthesis_engine is not None,
    }


@app.get("/api/research/{person_name}/stream")
async def stream_research(person_name: str, image_url: str | None = None):
    """SSE endpoint: stream research results as they arrive.

    Events:
      - init: {person_id, live_session_id, live_url} — sent first
      - result: AgentResult JSON — sent per agent
      - complete: {} — sent when all agents finish

    Frontend can consume with EventSource or fetch + ReadableStream.
    """
    if not deep_researcher:
        raise HTTPException(
            status_code=503,
            detail="Browser Use API key not configured — streaming unavailable",
        )

    import json as _json

    async def event_generator():
        # 1. Create person in Convex so frontend can subscribe
        person_id = None
        try:
            person_id = await db_gateway.store_person(
                f"stream_{uuid4().hex[:12]}",
                {
                    "name": person_name,
                    "photoUrl": image_url or "",
                    "confidence": 0.9,
                    "status": "researching",
                },
            )
        except Exception as exc:
            logger.warning("Failed to create person in Convex: {}", exc)

        # Send init event IMMEDIATELY so frontend gets feedback right away
        yield {
            "event": "init",
            "data": _json.dumps({
                "person_id": person_id,
                "person_name": person_name,
                "live_session_id": None,
                "live_url": None,
            }),
        }
        logger.info("SSE stream started for {}", person_name)

        # 2. Spawn live Browser Use session (X/Twitter) in background — don't block pipeline
        live_session_id = None
        live_url = None

        async def spawn_live_session():
            nonlocal live_session_id, live_url
            try:
                twitter_cfg = SOURCE_CONFIGS["twitter"]
                session = await bu_client.create_session(start_url=twitter_cfg["start_url"])
                live_session_id = session["id"]
                live_url = session.get("liveUrl")
                prompt = twitter_cfg["prompt"].replace("{name}", person_name)
                await bu_client.create_task(
                    session_id=live_session_id,
                    task=prompt,
                    start_url=twitter_cfg["start_url"],
                )
                logger.info("Live X session started: {} url={}", live_session_id, live_url)
            except Exception as exc:
                logger.warning("Failed to spawn live X session: {}", exc)

        # Launch session spawn in background — doesn't block research
        import asyncio as _asyncio
        _asyncio.create_task(spawn_live_session())

        # 3. Stream research results
        all_snippets: list[str] = []
        all_urls: list[str] = []
        all_sources: list[str] = []
        agent_data: dict[str, str] = {}

        async for result in pipeline.stream_research(person_name, person_id):
            all_snippets.extend(result.snippets[:3])
            all_urls.extend(result.urls_found[:5])
            all_sources.append(result.agent_name)
            # Collect full agent output for richer synthesis
            agent_data[result.agent_name] = "\n".join(result.snippets[:10])
            yield {
                "event": "result",
                "data": result.model_dump_json(),
            }

        # 4. Run synthesis on collected data and push dossier to Convex
        if person_id and synthesis_engine:
            try:
                from synthesis.models import SynthesisRequest
                from synthesis.models import SocialProfile as SynthSocialProfile

                synth_request = SynthesisRequest(
                    person_name=person_name,
                    enrichment_snippets=all_snippets[:50],
                    social_profiles=[],
                    raw_agent_data=agent_data,
                )
                synth_result = await synthesis_engine.synthesize(synth_request)
                if synth_result.success and synth_result.dossier:
                    dossier = synth_result.dossier
                    await db_gateway.update_person(person_id, {
                        "status": "enriched",
                        "summary": synth_result.summary,
                        "occupation": synth_result.occupation,
                        "organization": synth_result.organization,
                        "dossier": dossier.model_dump(),
                    })
                    yield {
                        "event": "dossier",
                        "data": _json.dumps(dossier.to_frontend_dict()),
                    }
            except Exception as exc:
                logger.error("Synthesis failed during stream: {}", exc)

        yield {"event": "complete", "data": _json.dumps({
            "person_id": person_id,
            "total_sources": len(all_sources),
            "total_urls": len(all_urls),
        })}

    return EventSourceResponse(event_generator())


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


# --- Browser Use Webhooks for observability ---


@app.post("/api/webhooks/browser-use")
async def browser_use_webhook(request: Request):
    """Receive Browser Use task status updates for observability.

    Events: agent.task.status_update (started, finished, stopped)
    Configure at: cloud.browser-use.com/settings?tab=webhooks
    """
    import hashlib
    import hmac
    import json as _json

    body = await request.body()

    # Signature verification (optional — skip if no secret configured)
    signature = request.headers.get("X-Webhook-Signature")
    webhook_secret = getattr(settings, "browser_use_webhook_secret", None)
    if webhook_secret and signature:
        expected = hmac.new(
            webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logger.warning("Browser Use webhook: invalid signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = _json.loads(body)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type", "unknown")
    timestamp = payload.get("timestamp", "")
    data = payload.get("payload", {})
    task_id = data.get("taskId", "")
    status = data.get("status", "")
    session_id = data.get("sessionId", "")

    logger.info(
        "BU webhook: type={} task={} status={} session={} at={}",
        event_type, task_id[:12], status, session_id[:12], timestamp,
    )

    # Push to Convex for real-time observability in frontend
    if event_type == "agent.task.status_update" and convex_gw.configured:
        try:
            await convex_gw.store_intel_fragment(
                person_id="__system__",
                source=f"browser_use:{status}",
                content=f"Task {task_id[:12]} → {status}",
                data_type="agent_event",
            )
        except Exception as exc:
            logger.warning("Failed to push BU webhook to Convex: {}", exc)

    return {"ok": True}
