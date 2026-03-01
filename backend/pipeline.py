from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import uuid4

from loguru import logger

from agents.models import OrchestratorResult, ResearchRequest
from agents.orchestrator import ResearchOrchestrator
from capture.frame_extractor import extract_frames
from db import DatabaseGateway
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest, EnrichmentResult
from identification import FaceDetector
from identification.embedder import ArcFaceEmbedder
from identification.models import FaceDetectionRequest, FaceSearchRequest
from identification.search_manager import FaceSearchManager
from observability.laminar import traced
from synthesis.connections import detect_connections
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
        synthesis_engine: GeminiSynthesisEngine | None = None,
    ) -> None:
        self._detector = detector
        self._embedder = embedder
        self._db = db
        self._face_searcher = face_searcher
        self._exa = exa_client
        self._orchestrator = orchestrator
        self._synthesis = synthesis_engine

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

                # Generate embedding
                embedding = self._embedder.embed(face, frame_bytes)

                # Step 3.5: Face search — identify who this person is
                resolved_name = person_name  # Use provided name as default
                if not resolved_name and self._face_searcher:
                    resolved_name = await self._identify_face(
                        embedding, frame_bytes,
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
                    person_identities[person_id] = (resolved_name, frame_bytes)

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

        # Synthesize with Gemini
        if not self._synthesis:
            logger.warning("No synthesis engine configured, skipping for {}", person_id)
            await self._db.update_person(person_id, {"status": "enriched_no_synthesis"})
            return False

        synthesis_result = await self._synthesis.synthesize(synthesis_request)

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
        if synthesis_result.dossier:
            update_data["dossier"] = synthesis_result.dossier.model_dump()

        await self._db.update_person(person_id, update_data)

        # Detect connections against all existing persons
        if synthesis_result.dossier:
            await self._detect_and_store_connections(person_id, synthesis_result.dossier)

        logger.info(
            "Enrichment complete for person={} name={}",
            person_id, person_name,
        )
        return True

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
        if not self._orchestrator:
            return None
        return await self._orchestrator.research_person(
            ResearchRequest(person_name=person_name),
        )

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
