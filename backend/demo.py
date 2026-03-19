# RESEARCH: rich (31k+ stars) for terminal output, httpx for image download
# DECISION: Using rich Console + Panel + Table for impressive live demo output
# ALT: Plain print + ANSI codes (simpler but less visually impressive for judges)
"""
JARVIS Live Demo Script
========================

Runs the full pipeline end-to-end with live stage-by-stage output.
Designed for judges to watch during the hackathon demo.

Usage:
    python demo.py                          # default: Sam Altman
    python demo.py --name "Jensen Huang"    # custom person
    python demo.py --image face.jpg         # use local image
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx
from loguru import logger
from rich.console import Console
from rich.panel import Panel

from config import get_settings
from enrichment.exa_client import ExaEnrichmentClient
from enrichment.models import EnrichmentRequest
from identification.detector import MediaPipeFaceDetector
from identification.embedder import ArcFaceEmbedder
from identification.models import FaceDetectionRequest
from pipeline import CapturePipeline
from synthesis.anthropic_engine import AnthropicSynthesisEngine
from synthesis.engine import GeminiSynthesisEngine
from synthesis.models import DossierReport

console = Console()

# Well-known face image URLs for demo subjects (public domain / press photos)
DEFAULT_FACE_URLS: dict[str, str] = {
    "Sam Altman": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5e/Sam_Altman_CropEdit.jpg/440px-Sam_Altman_CropEdit.jpg",
    "Jensen Huang": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e5/Jensen_Huang_CEO_of_Nvidia.jpg/440px-Jensen_Huang_CEO_of_Nvidia.jpg",
    "Dario Amodei": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f5/Dario_Amodei_at_REAIM_2023_%28cropped%29.jpg/440px-Dario_Amodei_at_REAIM_2023_%28cropped%29.jpg",
}


# ---------------------------------------------------------------------------
# Stage timing helper
# ---------------------------------------------------------------------------

class StageTimer:
    """Context manager that times a named pipeline stage and prints status."""

    def __init__(self, stage_name: str, stage_num: int, total_stages: int) -> None:
        self._name = stage_name
        self._num = stage_num
        self._total = total_stages
        self._start = 0.0
        self.elapsed = 0.0

    def __enter__(self) -> StageTimer:
        console.print(
            f"\n[bold cyan][{self._num}/{self._total}][/bold cyan] "
            f"[yellow]{self._name}[/yellow] ...",
        )
        self._start = time.monotonic()
        return self

    def __exit__(self, *_exc) -> None:
        self.elapsed = time.monotonic() - self._start
        console.print(
            f"    [green]Done[/green] in [bold]{self.elapsed:.1f}s[/bold]",
        )


# ---------------------------------------------------------------------------
# Image acquisition
# ---------------------------------------------------------------------------

async def get_face_image(person_name: str, image_path: str | None = None) -> bytes:
    """Download or load a face image for the demo subject."""
    if image_path:
        path = Path(image_path)
        if not path.exists():
            console.print(f"[red]Image not found: {image_path}[/red]")
            sys.exit(1)
        return path.read_bytes()

    url = DEFAULT_FACE_URLS.get(person_name)
    if not url:
        console.print(
            f"[yellow]No default image URL for '{person_name}'. "
            f"Skipping face detection, running enrichment + synthesis only.[/yellow]",
        )
        return b""

    async with httpx.AsyncClient(
        follow_redirects=True, timeout=15.0,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    ) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError:
            console.print(
                f"    [yellow]Image download failed ({resp.status_code}), "
                f"skipping face detection[/yellow]",
            )
            return b""


# ---------------------------------------------------------------------------
# Pretty-print dossier
# ---------------------------------------------------------------------------

def render_dossier(dossier: DossierReport, person_name: str) -> None:
    """Render a DossierReport as a rich Panel with colored sections."""

    # Header
    title_line = f"[bold]{person_name}[/bold]"
    if dossier.title:
        title_line += f" — {dossier.title}"
    if dossier.company:
        title_line += f" @ {dossier.company}"

    sections: list[str] = []

    # Summary
    if dossier.summary:
        sections.append(f"[bold white]Summary[/bold white]\n{dossier.summary}")

    # Work History
    if dossier.work_history:
        wh_lines = []
        for entry in dossier.work_history:
            line = f"  [cyan]{entry.role}[/cyan] at [bold]{entry.company}[/bold]"
            if entry.period:
                line += f" ({entry.period})"
            wh_lines.append(line)
        sections.append("[bold white]Work History[/bold white]\n" + "\n".join(wh_lines))

    # Education
    if dossier.education:
        ed_lines = []
        for entry in dossier.education:
            line = f"  [cyan]{entry.school}[/cyan]"
            if entry.degree:
                line += f" — {entry.degree}"
            ed_lines.append(line)
        sections.append("[bold white]Education[/bold white]\n" + "\n".join(ed_lines))

    # Social Profiles
    sp = dossier.social_profiles
    social_lines = []
    if sp.linkedin:
        social_lines.append(f"  LinkedIn: [blue]{sp.linkedin}[/blue]")
    if sp.twitter:
        social_lines.append(f"  Twitter:  [blue]{sp.twitter}[/blue]")
    if sp.instagram:
        social_lines.append(f"  Instagram:[blue] {sp.instagram}[/blue]")
    if sp.github:
        social_lines.append(f"  GitHub:   [blue]{sp.github}[/blue]")
    if sp.website:
        social_lines.append(f"  Website:  [blue]{sp.website}[/blue]")
    if social_lines:
        sections.append("[bold white]Social Profiles[/bold white]\n" + "\n".join(social_lines))

    # Notable Activity
    if dossier.notable_activity:
        items = "\n".join(f"  [green]>[/green] {a}" for a in dossier.notable_activity)
        sections.append(f"[bold white]Notable Activity[/bold white]\n{items}")

    # Conversation Hooks
    if dossier.conversation_hooks:
        items = "\n".join(f"  [magenta]>[/magenta] {h}" for h in dossier.conversation_hooks)
        sections.append(f"[bold white]Conversation Hooks[/bold white]\n{items}")

    # Risk Flags
    if dossier.risk_flags:
        items = "\n".join(f"  [red]![/red] {r}" for r in dossier.risk_flags)
        sections.append(f"[bold white]Risk Flags[/bold white]\n{items}")

    body = "\n\n".join(sections)
    console.print(Panel(body, title=title_line, border_style="bright_green", padding=(1, 2)))


# ---------------------------------------------------------------------------
# Main demo flow
# ---------------------------------------------------------------------------

async def run_demo(person_name: str, image_path: str | None = None) -> None:
    """Execute the full JARVIS pipeline with live output."""
    total_start = time.monotonic()
    settings = get_settings()
    total_stages = 6

    console.print(Panel(
        f"[bold white]JARVIS[/bold white] — Real-Time Person Intelligence\n"
        f"Subject: [bold cyan]{person_name}[/bold cyan]",
        border_style="bright_blue",
    ))

    # Stage 1: Acquire image
    with StageTimer("Acquiring face image", 1, total_stages):
        image_data = await get_face_image(person_name, image_path)
        if image_data:
            console.print(f"    Image size: {len(image_data):,} bytes")

    # Stage 2: Face detection
    faces_detected = 0
    if image_data:
        with StageTimer("Face detection (MediaPipe)", 2, total_stages) as _t:
            detector = MediaPipeFaceDetector()
            if detector.configured:
                request = FaceDetectionRequest(image_data=image_data)
                result = await detector.detect_faces(request)
                faces_detected = len(result.faces)
                console.print(
                    f"    Faces found: [bold]{faces_detected}[/bold] "
                    f"({result.frame_width}x{result.frame_height})",
                )
                if result.faces:
                    for i, face in enumerate(result.faces):
                        console.print(
                            f"    Face {i+1}: confidence={face.confidence:.2f} "
                            f"bbox=({face.bbox.x:.2f}, {face.bbox.y:.2f})",
                        )
            else:
                console.print("    [yellow]Detector model not found, skipping[/yellow]")
    else:
        console.print(
            f"\n[bold cyan][2/{total_stages}][/bold cyan] "
            f"[dim]Face detection skipped (no image)[/dim]",
        )

    # Stage 3: Embedding
    if image_data and faces_detected > 0:
        with StageTimer("Face embedding (ArcFace)", 3, total_stages):
            embedder = ArcFaceEmbedder()
            embedding = embedder.embed(result.faces[0], image_data)
            console.print(f"    Embedding dim: {len(embedding)}")
    else:
        console.print(
            f"\n[bold cyan][3/{total_stages}][/bold cyan] "
            f"[dim]Embedding skipped (no faces)[/dim]",
        )

    # Stage 4: Exa enrichment
    exa_result = None
    with StageTimer("Exa enrichment (fast pass)", 4, total_stages):
        if settings.exa_api_key:
            exa_client = ExaEnrichmentClient(settings)
            exa_result = await exa_client.enrich_person(
                EnrichmentRequest(name=person_name),
            )
            if exa_result.success:
                console.print(f"    Hits: [bold]{len(exa_result.hits)}[/bold]")
                for hit in exa_result.hits[:3]:
                    console.print(f"    [dim]{hit.title[:60]}[/dim]")
            else:
                console.print(f"    [red]Failed: {exa_result.error}[/red]")
        else:
            console.print("    [yellow]EXA_API_KEY not set, skipping[/yellow]")

    # Stage 5: Synthesis
    dossier: DossierReport | None = None
    with StageTimer("Synthesis (Claude / Gemini)", 5, total_stages):
        synthesis_request = CapturePipeline._merge_to_synthesis_request(
            person_name, exa_result, None,
        )

        # Try Anthropic first, fall back to Gemini
        engine = AnthropicSynthesisEngine(settings)
        if engine.configured:
            console.print("    Engine: [bold]Claude (Anthropic)[/bold]")
            synth_result = await engine.synthesize(synthesis_request)
        elif settings.gemini_api_key:
            console.print("    Engine: [bold]Gemini (fallback)[/bold]")
            gemini = GeminiSynthesisEngine(settings)
            synth_result = await gemini.synthesize(synthesis_request)
        else:
            console.print("    [red]No synthesis engine configured[/red]")
            synth_result = None

        if synth_result and synth_result.success:
            dossier = synth_result.dossier
            console.print(f"    Confidence: [bold]{synth_result.confidence_score:.0%}[/bold]")
        elif synth_result:
            console.print(f"    [red]Synthesis failed: {synth_result.error}[/red]")

    # Stage 6: Render dossier
    with StageTimer("Rendering dossier", 6, total_stages):
        if dossier:
            render_dossier(dossier, person_name)
        else:
            console.print("    [red]No dossier to render[/red]")

    # Final timing
    total_elapsed = time.monotonic() - total_start
    console.print(
        f"\n[bold green]Pipeline complete[/bold green] in "
        f"[bold]{total_elapsed:.1f}s[/bold]",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="JARVIS Live Demo — full pipeline with live output",
    )
    parser.add_argument(
        "--name", type=str, default="Sam Altman",
        help="Person to investigate (default: Sam Altman)",
    )
    parser.add_argument(
        "--image", type=str, default=None,
        help="Path to a local face image (optional)",
    )
    args = parser.parse_args()

    # Suppress loguru to keep demo output clean (rich handles all output)
    logger.remove()

    asyncio.run(run_demo(args.name, args.image))


if __name__ == "__main__":
    main()
