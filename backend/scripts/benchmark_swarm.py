#!/usr/bin/env python3
"""Benchmark harness for JARVIS research swarm.

Runs Exa enrichment AND orchestrator swarm in parallel for each person,
collects per-agent timing/status/counts, and outputs a rich formatted table.

Usage:
    python scripts/benchmark_swarm.py "Sam Altman" "Elon Musk"
    python scripts/benchmark_swarm.py  # uses defaults
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

# -- sys.path setup so imports resolve from project root --
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from rich.console import Console  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from agents.models import OrchestratorResult, ResearchRequest  # noqa: E402
from agents.orchestrator import ResearchOrchestrator  # noqa: E402
from config import get_settings  # noqa: E402

DEFAULT_NAMES = [
    "Sam Altman",
    "Dario Amodei",
    "Garry Tan",
    "Jensen Huang",
    "Satya Nadella",
]

console = Console()


# ── per-person benchmark ────────────────────────────────────────────

async def _benchmark_one(
    name: str,
    orchestrator: ResearchOrchestrator,
) -> dict:
    """Run orchestrator (Exa + static agents + dynamic scrapers) for a single person."""
    request = ResearchRequest(person_name=name, timeout_seconds=120)

    wall_start = time.monotonic()
    orch_result: OrchestratorResult = await orchestrator.research_person(request)
    wall_seconds = time.monotonic() - wall_start

    agent_rows: list[dict] = []
    for agent_name, ar in orch_result.agent_results.items():
        agent_rows.append({
            "agent": agent_name,
            "status": ar.status.value,
            "profiles": len(ar.profiles),
            "snippets": len(ar.snippets),
            "duration_s": round(ar.duration_seconds, 2),
            "error": ar.error,
        })

    return {
        "person": name,
        "wall_seconds": round(wall_seconds, 2),
        "orchestrator_success": orch_result.success,
        "total_profiles": len(orch_result.all_profiles),
        "total_snippets": len(orch_result.all_snippets),
        "agents": agent_rows,
    }


# ── display helpers ─────────────────────────────────────────────────

STATUS_COLOR = {
    "success": "green",
    "failed": "red",
    "timeout": "yellow",
    "pending": "dim",
    "running": "cyan",
}


def _print_person_table(result: dict) -> None:
    table = Table(
        title=f"[bold]{result['person']}[/bold]  ({result['wall_seconds']}s wall)",
        show_lines=True,
    )
    table.add_column("Agent", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Profiles", justify="right")
    table.add_column("Snippets", justify="right")
    table.add_column("Duration (s)", justify="right")
    table.add_column("Error")

    for row in result["agents"]:
        color = STATUS_COLOR.get(row["status"], "white")
        table.add_row(
            row["agent"],
            f"[{color}]{row['status']}[/{color}]",
            str(row["profiles"]),
            str(row["snippets"]),
            str(row["duration_s"]),
            (row["error"] or "")[:60],
        )

    console.print(table)
    console.print()


def _print_summary(results: list[dict], total_wall: float) -> None:
    all_agents: dict[str, dict[str, int]] = {}
    for r in results:
        for a in r["agents"]:
            name = a["agent"]
            if name not in all_agents:
                all_agents[name] = {"success": 0, "failed": 0, "timeout": 0, "total": 0}
            all_agents[name]["total"] += 1
            if a["status"] == "success":
                all_agents[name]["success"] += 1
            elif a["status"] == "timeout":
                all_agents[name]["timeout"] += 1
            else:
                all_agents[name]["failed"] += 1

    table = Table(title="[bold]Agent Success Rates[/bold]", show_lines=True)
    table.add_column("Agent", style="bold")
    table.add_column("Success", justify="center", style="green")
    table.add_column("Failed", justify="center", style="red")
    table.add_column("Timeout", justify="center", style="yellow")
    table.add_column("Rate", justify="center")

    for agent, counts in sorted(all_agents.items()):
        rate = counts["success"] / counts["total"] * 100 if counts["total"] else 0
        rate_color = "green" if rate >= 75 else "yellow" if rate >= 50 else "red"
        table.add_row(
            agent,
            str(counts["success"]),
            str(counts["failed"]),
            str(counts["timeout"]),
            f"[{rate_color}]{rate:.0f}%[/{rate_color}]",
        )

    console.print(table)

    total_profiles = sum(r["total_profiles"] for r in results)
    total_snippets = sum(r["total_snippets"] for r in results)
    console.print(
        Panel(
            f"[bold]People:[/bold] {len(results)}  |  "
            f"[bold]Profiles:[/bold] {total_profiles}  |  "
            f"[bold]Snippets:[/bold] {total_snippets}  |  "
            f"[bold]Total wall time:[/bold] {total_wall:.1f}s",
            title="Overall",
        )
    )


# ── main ────────────────────────────────────────────────────────────

async def main(names: list[str]) -> None:
    settings = get_settings()
    orchestrator = ResearchOrchestrator(settings)

    flags = settings.service_flags()
    console.print(Panel(
        "\n".join(f"  {svc}: [{'green' if ok else 'red'}]{ok}[/]" for svc, ok in sorted(flags.items())),  # noqa: E501
        title="[bold]Service Flags[/bold]",
    ))

    console.print(f"\n[bold]Benchmarking {len(names)} people:[/bold] {', '.join(names)}\n")

    results: list[dict] = []
    overall_start = time.monotonic()

    for name in names:
        console.rule(f"[bold cyan]{name}[/bold cyan]")
        try:
            result = await _benchmark_one(name, orchestrator)
            results.append(result)
            _print_person_table(result)
        except Exception as e:
            console.print(f"[red bold]FATAL for {name}:[/red bold] {e}")
            results.append({
                "person": name,
                "wall_seconds": 0,
                "orchestrator_success": False,
                "total_profiles": 0,
                "total_snippets": 0,
                "agents": [],
                "error": str(e),
            })

    total_wall = time.monotonic() - overall_start

    console.rule("[bold magenta]Summary[/bold magenta]")
    _print_summary(results, total_wall)

    out_path = _PROJECT_ROOT / "benchmark_results.json"
    payload = {
        "total_wall_seconds": round(total_wall, 2),
        "people_count": len(names),
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2, default=str))
    console.print(f"\n[dim]Results saved to {out_path}[/dim]")


if __name__ == "__main__":
    names = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_NAMES
    asyncio.run(main(names))
