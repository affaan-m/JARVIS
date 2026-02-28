from __future__ import annotations

from schemas import TaskPhase

TASK_PHASES: list[TaskPhase] = [
    TaskPhase(
        id="foundation",
        title="Foundation",
        timebox="Hours 0-4",
        tasks=[
            {
                "id": "T01",
                "title": "Convex project setup",
                "area": "realtime",
                "status": "in_progress",
                "acceptance": (
                    "Schema and mutations are scaffolded and ready for codegen "
                    "once Convex is linked."
                ),
                "notes": (
                    "Schema and function files exist in frontend/convex; "
                    "project linking is the remaining step."
                ),
            },
            {
                "id": "T02",
                "title": "FastAPI skeleton",
                "area": "backend",
                "status": "done",
                "acceptance": (
                    "Health, capture, task, and service-readiness endpoints "
                    "return typed responses."
                ),
                "notes": (
                    "Implemented in backend/main.py with settings-driven "
                    "readiness reporting."
                ),
            },
            {
                "id": "T03",
                "title": "Next.js project setup",
                "area": "frontend",
                "status": "done",
                "acceptance": (
                    "Next.js app renders the SPECTER war-room shell with fonts, "
                    "layout, and local demo data."
                ),
                "notes": (
                    "Frontend now builds without waiting on live Convex codegen."
                ),
            },
            {
                "id": "T04",
                "title": "Convex ↔ Frontend proof of life",
                "area": "frontend",
                "status": "pending",
                "acceptance": (
                    "Button click inserts and streams a real person record "
                    "from Convex in under 1 second."
                ),
                "notes": (
                    "Blocked on linking a real Convex deployment and generating "
                    "typed client artifacts."
                ),
            },
        ],
    ),
    TaskPhase(
        id="pipelines",
        title="Pipelines",
        timebox="Hours 4-14",
        tasks=[
            {
                "id": "T05-T08",
                "title": "Identification pipeline",
                "area": "backend",
                "status": "pending",
                "acceptance": (
                    "Photo or video upload flows through capture, "
                    "identification, and person creation."
                ),
            },
            {
                "id": "T09-T13",
                "title": "Agent swarm",
                "area": "backend",
                "status": "pending",
                "acceptance": (
                    "Fast-pass enrichment and browser agents stream results "
                    "into the board."
                ),
            },
        ],
    ),
    TaskPhase(
        id="quality",
        title="Quality and Delivery",
        timebox="Continuous",
        tasks=[
            {
                "id": "Q01",
                "title": "CI, code scanning, and dependency review",
                "area": "github",
                "status": "done",
                "acceptance": (
                    "PRs and pushes run repeatable checks and security review "
                    "workflows in GitHub Actions."
                ),
                "notes": (
                    "CI, CodeQL, dependency review, and deploy workflows are "
                    "in .github/workflows."
                ),
            }
        ],
    ),
]
