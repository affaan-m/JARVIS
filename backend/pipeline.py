from __future__ import annotations

import asyncio
import io
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from uuid import uuid4

from loguru import logger
from PIL import Image

from typing import Any

from agents.deep_researcher import DeepResearcher
from agents.models import AgentResult, AgentStatus, OrchestratorResult, ResearchRequest
from agents.orchestrator import ResearchOrchestrator
from capture.frame_extractor import extract_frames
from db import DatabaseGateway
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest, EnrichmentResult
from identification import FaceDetector
from identification.embedder import ArcFaceEmbedder
from identification.models import BoundingBox, FaceDetectionRequest, FaceSearchRequest
from identification.search_manager import FaceSearchManager
from memory.supermemory_client import SuperMemoryClient
from observability.laminar import traced
from synthesis.connections import detect_connections
from synthesis.anthropic_engine import AnthropicSynthesisEngine
from synthesis.engine import GeminiSynthesisEngine
from synthesis.models import DossierReport
from synthesis.models import SocialProfile as SynthSocialProfile
from synthesis.models import SynthesisRequest


@dataclass(frozen=True)
class PipelineResult:
    """Result of processing a single capture through the pipeline."""

    capture_id: str
    total_frames: int = 0
    faces_detected: int = 0
    persons_created: list[str] = field(default_factory=list)
    persons_enriched: int = 0
    success: bool = True
    error: str | None = None


class CapturePipeline:
    """End-to-end pipeline: capture -> detect -> embed -> enrich -> synthesize -> store."""

    def __init__(
        self,
        *,
        detector: FaceDetector,
        embedder: ArcFaceEmbedder,
        db: DatabaseGateway,
        face_searcher: FaceSearchManager | None = None,
        exa_client: ExaEnrichmentClient | None = None,
        orchestrator: ResearchOrchestrator | None = None,
        synthesis_engine: AnthropicSynthesisEngine | GeminiSynthesisEngine | None = None,
        synthesis_fallback: GeminiSynthesisEngine | AnthropicSynthesisEngine | None = None,
        supermemory: SuperMemoryClient | None = None,
    ) -> None:
        self._detector = detector
        self._embedder = embedder
        self._db = db
        self._face_searcher = face_searcher
        self._exa = exa_client
        self._orchestrator = orchestrator
        self._synthesis = synthesis_engine
        self._synthesis_fallback = synthesis_fallback
        self._supermemory = supermemory
        self._deep_researcher: DeepResearcher | None = None

    @traced("pipeline.process")
    async def process(
        self,
        capture_id: str,
        data: bytes,
        content_type: str,
        source: str = "manual_upload",
        person_name: str | None = None,
    ) -> PipelineResult:
        """Run the full capture-to-dossier pipeline.

        1. Extract frames from the uploaded media
        2. Detect faces in each frame
        3. Generate embeddings for each face
        4. Create person records in the database
        5. Enrich + research + synthesize for each person (parallel, error-isolated)
        """
        logger.info(
            "Pipeline started for capture={} type={} source={}",
            capture_id, content_type, source,
        )

        # Store capture metadata
        await self._db.store_capture(capture_id, {
            "content_type": content_type,
            "source": source,
            "status": "processing",
        })

        # Step 1: Frame extraction
        try:
            frames = extract_frames(data, content_type)
        except Exception as exc:
            logger.error("Frame extraction failed for {}: {}", capture_id, exc)
            return PipelineResult(
                capture_id=capture_id, success=False,
                error=f"Frame extraction failed: {exc}",
            )

        if not frames:
            logger.warning("No frames extracted from capture={}", capture_id)
            return PipelineResult(capture_id=capture_id, total_frames=0, success=True)

        logger.info("Extracted {} frame(s) from capture={}", len(frames), capture_id)

        # Step 2 + 3 + 4: Detect, embed, face-search, store for each frame
        total_faces = 0
        persons_created: list[str] = []
        # Maps person_id -> (resolved_name, face_image_bytes)
        person_identities: dict[str, tuple[str, bytes]] = {}

        for frame_idx, frame_bytes in enumerate(frames):
            request = FaceDetectionRequest(image_data=frame_bytes)
            detection_result = await self._detector.detect_faces(request)

            if not detection_result.success:
                logger.warning(
                    "Detection failed on frame {} of capture={}: {}",
                    frame_idx, capture_id, detection_result.error,
                )
                continue

            for face in detection_result.faces:
                total_faces += 1

                # Crop face from frame for downstream use (search, thumbnails)
                cropped_bytes = self._crop_face(
                    frame_bytes, face.bbox,
                    detection_result.frame_width,
                    detection_result.frame_height,
                )
                face_image = cropped_bytes or frame_bytes

                # Generate embedding
                embedding = self._embedder.embed(face, frame_bytes)

                # Step 3.5: Face search — identify who this person is
                resolved_name = person_name  # Use provided name as default
                if not resolved_name and self._face_searcher:
                    resolved_name = await self._identify_face(
                        embedding, face_image,
                    )

                # Create person record
                person_id = f"person_{uuid4().hex[:12]}"
                person_data: dict = {
                    "capture_id": capture_id,
                    "frame_index": frame_idx,
                    "bbox": face.bbox.model_dump(),
                    "confidence": face.confidence,
                    "embedding": embedding,
                    "status": "detected",
                }
                if resolved_name:
                    person_data["name"] = resolved_name
                    person_data["status"] = "identified"

                await self._db.store_person(person_id, person_data)
                persons_created.append(person_id)

                if resolved_name:
                    person_identities[person_id] = (resolved_name, face_image)

                logger.info(
                    "Created person={} name={} from capture={} frame={} confidence={:.2f}",
                    person_id, resolved_name or "unknown",
                    capture_id, frame_idx, face.confidence,
                )

        # Step 5: Enrich + research + synthesize each identified person (error-isolated)
        persons_enriched = 0
        if person_identities:
            enrichment_tasks = [
                self._enrich_person(pid, name)
                for pid, (name, _img) in person_identities.items()
            ]
            pids = list(person_identities.keys())
            results = await asyncio.gather(*enrichment_tasks, return_exceptions=True)
            for pid, result in zip(pids, results, strict=True):
                if isinstance(result, Exception):
                    logger.error("Enrichment crashed for person={}: {}", pid, result)
                elif result:
                    persons_enriched += 1

        # Update capture status
        await self._db.store_capture(capture_id, {
            "content_type": content_type,
            "source": source,
            "status": "completed",
            "total_frames": len(frames),
            "faces_detected": total_faces,
            "persons_created": persons_created,
        })

        logger.info(
            "Pipeline complete for capture={}: {} frames, {} faces, {} persons, {} enriched",
            capture_id, len(frames), total_faces, len(persons_created), persons_enriched,
        )

        return PipelineResult(
            capture_id=capture_id,
            total_frames=len(frames),
            faces_detected=total_faces,
            persons_created=persons_created,
            persons_enriched=persons_enriched,
            success=True,
        )

    @staticmethod
    def _crop_face(
        frame_bytes: bytes,
        bbox: BoundingBox,
        frame_width: int,
        frame_height: int,
    ) -> bytes | None:
        """Crop a face region from the frame using normalized bbox coords.

        Returns JPEG bytes of the cropped face, or None if cropping fails.
        """
        if frame_width <= 0 or frame_height <= 0:
            return None
        try:
            img = Image.open(io.BytesIO(frame_bytes))
            w, h = img.size

            left = int(bbox.x * w)
            upper = int(bbox.y * h)
            right = int((bbox.x + bbox.width) * w)
            lower = int((bbox.y + bbox.height) * h)

            # Clamp to image bounds
            left = max(0, left)
            upper = max(0, upper)
            right = min(w, right)
            lower = min(h, lower)

            if right <= left or lower <= upper:
                return None

            cropped = img.crop((left, upper, right, lower))
            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
        except Exception as exc:
            logger.warning("Face crop failed: {}", exc)
            return None

    @traced("pipeline.identify_face")
    async def _identify_face(
        self, embedding: list[float], image_data: bytes
    ) -> str | None:
        """Use face search to identify a person from their face image.

        Returns the best-guess person name, or None if search fails.
        """
        if not self._face_searcher:
            return None

        try:
            search_request = FaceSearchRequest(
                embedding=embedding,
                image_data=image_data,
            )
            search_result = await self._face_searcher.search_face(search_request)

            if not search_result.success:
                logger.warning("Face search failed: {}", search_result.error)
                return None

            name = self._face_searcher.best_name_from_results(search_result)
            if name:
                logger.info("Face search identified person as: {}", name)
            else:
                logger.info("Face search found {} matches but no name", len(search_result.matches))

            return name

        except Exception as exc:
            logger.error("Face search crashed: {}", exc)
            return None

    @traced("pipeline.enrich_person")
    async def _enrich_person(self, person_id: str, person_name: str) -> bool:
        """Run Exa enrichment + browser research in parallel, then synthesize.

        Returns True if synthesis produced a dossier, False otherwise.
        All failures are logged but never raised — caller uses return_exceptions anyway.
        """
        # Check SuperMemory cache before running expensive enrichment
        cached_dossier = await self._check_supermemory_cache(person_name)
        if cached_dossier is not None:
            logger.info(
                "SuperMemory cache hit for person={} name={}, skipping enrichment",
                person_id, person_name,
            )
            await self._db.update_person(person_id, {
                "status": "enriched",
                "summary": cached_dossier.get("summary", ""),
                "occupation": cached_dossier.get("occupation", ""),
                "organization": cached_dossier.get("organization", ""),
                "dossier": cached_dossier,
                "source": "supermemory_cache",
            })
            return True

        await self._db.update_person(person_id, {"status": "enriching"})

        # Fan out Exa + browser research in parallel
        exa_coro = self._run_exa(person_name)
        browser_coro = self._run_browser_research(person_name)
        exa_result, browser_result = await asyncio.gather(
            exa_coro, browser_coro, return_exceptions=True,
        )

        # Handle exceptions from gather
        if isinstance(exa_result, Exception):
            logger.error("Exa enrichment crashed for {}: {}", person_id, exa_result)
            exa_result = None
        if isinstance(browser_result, Exception):
            logger.error("Browser research crashed for {}: {}", person_id, browser_result)
            browser_result = None

        # Merge into a SynthesisRequest
        synthesis_request = self._merge_to_synthesis_request(
            person_name, exa_result, browser_result,
        )

        # Synthesize with primary engine, fall back to secondary on any failure
        if not self._synthesis:
            logger.warning("No synthesis engine configured, skipping for {}", person_id)
            await self._db.update_person(person_id, {"status": "enriched_no_synthesis"})
            return False

        synthesis_result = await self._synthesis.synthesize(synthesis_request)

        # If primary failed and we have a fallback engine, retry with it
        if (
            not synthesis_result.success
            and self._synthesis_fallback
            and self._synthesis_fallback.configured
        ):
            logger.warning(
                "Primary synthesis failed for person={} ({}), retrying with fallback engine",
                person_id, synthesis_result.error,
            )
            synthesis_result = await self._synthesis_fallback.synthesize(
                synthesis_request,
            )

        if not synthesis_result.success:
            logger.warning(
                "Synthesis failed for person={}: {}", person_id, synthesis_result.error,
            )
            await self._db.update_person(person_id, {
                "status": "synthesis_failed",
                "synthesis_error": synthesis_result.error,
            })
            return False

        # Update person with dossier
        update_data: dict = {
            "status": "enriched",
            "summary": synthesis_result.summary,
            "occupation": synthesis_result.occupation,
            "organization": synthesis_result.organization,
        }
        dossier_dict: dict[str, Any] | None = None
        if synthesis_result.dossier:
            dossier_dict = synthesis_result.dossier.model_dump()
            update_data["dossier"] = dossier_dict

        await self._db.update_person(person_id, update_data)

        # Cache successful dossier in SuperMemory for future lookups
        await self._store_supermemory_cache(person_name, update_data, dossier_dict)

        # Detect connections against all existing persons
        if synthesis_result.dossier:
            await self._detect_and_store_connections(person_id, synthesis_result.dossier)

        logger.info(
            "Enrichment complete for person={} name={}",
            person_id, person_name,
        )
        return True

    async def _check_supermemory_cache(self, person_name: str) -> dict[str, Any] | None:
        """Check SuperMemory for a cached dossier. Returns None on miss or error."""
        if not self._supermemory:
            return None
        try:
            return await self._supermemory.search_person(person_name)
        except Exception as exc:
            logger.error("SuperMemory cache check failed for {}: {}", person_name, exc)
            return None

    async def _store_supermemory_cache(
        self,
        person_name: str,
        update_data: dict[str, Any],
        dossier_dict: dict[str, Any] | None,
    ) -> None:
        """Store a completed dossier in SuperMemory for future cache hits."""
        if not self._supermemory:
            return
        cache_payload = {
            "summary": update_data.get("summary", ""),
            "occupation": update_data.get("occupation", ""),
            "organization": update_data.get("organization", ""),
        }
        if dossier_dict:
            cache_payload["dossier"] = dossier_dict
        try:
            await self._supermemory.store_dossier(person_name, cache_payload)
        except Exception as exc:
            logger.error("SuperMemory cache store failed for {}: {}", person_name, exc)

    async def _detect_and_store_connections(
        self, person_id: str, dossier: DossierReport,
    ) -> None:
        """Compare new person against all existing persons and store any connections."""
        try:
            existing = await self._db.list_persons_with_dossiers()
        except Exception as exc:
            logger.error("Failed to list persons for connection detection: {}", exc)
            return

        # Build list with person_id key expected by detect_connections
        existing_with_ids = []
        for p in existing:
            pid = p.get("_id") or p.get("person_id", "")
            existing_with_ids.append({**p, "person_id": pid})

        candidates = detect_connections(person_id, dossier, existing_with_ids)

        for candidate in candidates:
            try:
                await self._db.create_connection(
                    person_a_id=candidate.person_a_id,
                    person_b_id=candidate.person_b_id,
                    relationship_type=candidate.relationship_type,
                    description=candidate.description,
                )
                logger.info(
                    "Created connection: {} <-> {} ({})",
                    candidate.person_a_id, candidate.person_b_id,
                    candidate.relationship_type,
                )
            except Exception as exc:
                logger.error(
                    "Failed to store connection {} <-> {}: {}",
                    candidate.person_a_id, candidate.person_b_id, exc,
                )

    @traced("pipeline.exa_enrichment")
    async def _run_exa(self, person_name: str) -> EnrichmentResult | None:
        if not self._exa:
            return None
        return await self._exa.enrich_person(EnrichmentRequest(name=person_name))

    @traced("pipeline.browser_research")
    async def _run_browser_research(self, person_name: str) -> OrchestratorResult | None:
        """Run deep research using DeepResearcher (preferred) or old orchestrator (fallback)."""
        if self._deep_researcher:
            # Use DeepResearcher: collect all results into an OrchestratorResult
            request = ResearchRequest(person_name=person_name)
            agent_results: dict[str, AgentResult] = {}
            all_profiles: list = []
            all_snippets: list[str] = []

            async for result in self._deep_researcher.research(request):
                agent_results[result.agent_name] = result
                all_profiles.extend(result.profiles)
                all_snippets.extend(result.snippets)

            return OrchestratorResult(
                person_name=person_name,
                agent_results=agent_results,
                all_profiles=all_profiles,
                all_snippets=all_snippets,
                success=bool(agent_results),
            )

        if not self._orchestrator:
            return None
        return await self._orchestrator.research_person(
            ResearchRequest(person_name=person_name),
        )

    async def stream_research(
        self,
        person_name: str,
        person_id: str | None = None,
    ) -> AsyncGenerator[AgentResult, None]:
        """Stream research results as an async generator for SSE endpoints.

        Optionally pushes each result to Convex as an intel fragment.
        """
        if not self._deep_researcher:
            return

        request = ResearchRequest(person_name=person_name)
        async for result in self._deep_researcher.research(request):
            # Skip internal meta results (phase timings) — not for display/storage
            if result.agent_name == "deep_researcher_meta":
                continue
            # Push to Convex as intel fragment if we have a person_id and a Convex gateway
            if person_id and hasattr(self._db, "store_intel_fragment"):
                content = " | ".join(result.snippets[:3]) if result.snippets else ""
                await self._db.store_intel_fragment(
                    person_id=person_id,
                    source=result.agent_name,
                    content=content[:1000],
                    urls=result.urls_found[:10],
                    confidence=result.confidence,
                )
            yield result

    @staticmethod
    def _merge_to_synthesis_request(
        person_name: str,
        exa_result: EnrichmentResult | None,
        browser_result: OrchestratorResult | None,
    ) -> SynthesisRequest:
        enrichment_snippets: list[str] = []
        social_profiles: list[SynthSocialProfile] = []
        raw_agent_data: dict[str, str] = {}

        # Merge Exa hits
        if exa_result and exa_result.success:
            for hit in exa_result.hits:
                snippet = f"[{hit.title}]({hit.url})"
                if hit.snippet:
                    snippet += f" — {hit.snippet}"
                enrichment_snippets.append(snippet)

        # Merge browser agent results
        if browser_result and browser_result.success:
            for profile in browser_result.all_profiles:
                social_profiles.append(
                    SynthSocialProfile(
                        platform=profile.platform,
                        url=profile.url,
                        username=profile.username,
                        bio=profile.bio,
                        followers=profile.followers,
                    )
                )
            enrichment_snippets.extend(browser_result.all_snippets)

            for agent_name, agent_result in browser_result.agent_results.items():
                if agent_result.snippets:
                    raw_agent_data[agent_name] = " | ".join(agent_result.snippets)

        return SynthesisRequest(
            person_name=person_name,
            enrichment_snippets=enrichment_snippets,
            social_profiles=social_profiles,
            raw_agent_data=raw_agent_data,
        )
