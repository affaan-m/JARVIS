# YC Hackathon Codex Guide

This file makes Codex behave consistently with the existing Claude project rules in [`.claude/CLAUDE.md`](/Users/affoon/Documents/GitHub/YC_hackathon/.claude/CLAUDE.md). If there is any conflict, use `.claude/CLAUDE.md` as the source of truth.

## Project

JARVIS is a real-time person intelligence platform for the Browser Use + YC web agents hackathon:

- Meta glasses or phone camera input
- Face detection and identification
- Browser-agent enrichment and report generation
- Corkboard-style frontend for live demo output

## Non-Negotiables

Before writing implementation code:

1. Search for existing maintained repos and libraries first.
2. Decide `use`, `fork + extend`, or `build`.
3. Prefer existing high-quality tools because this repo is in hackathon mode.

Do not change these architecture choices without explicit approval:

- Frontend: Next.js + Tailwind + Framer Motion on Vercel
- Backend: FastAPI
- Real-time: Convex
- Persistent storage: MongoDB Atlas
- Fast research: Exa API
- Deep research: Browser Use agent swarm
- Face pipeline: mediapipe or similar detect, ArcFace-style embeddings, reverse-image enrichment

## Build Priorities

Order of importance:

1. Demo-visible outcomes
2. Working fallbacks
3. Fast iteration
4. Code quality

The live demo matters more than broad feature count.

## Expected Structure

- `backend/capture`: camera input and frame extraction
- `backend/identification`: face detection, embeddings, lookups
- `backend/agents`: Browser Use agents and orchestration
- `backend/synthesis`: report generation
- `backend/enrichment`: Exa and other fast lookups
- `backend/db`: Convex and MongoDB integration
- `backend/observability`: Laminar and tracing
- `frontend/app`: Next.js routes
- `frontend/components`: UI pieces such as the corkboard and person cards
- `frontend/convex`: schema, queries, mutations
- `frontend/lib`: app utilities and animation helpers

## Before Implementing A Module

Read the matching docs first:

- `SYSTEM_DESIGN.md`
- `DESIGN_HANDOFF.md`
- `TECH_DOC.md`
- `TASKS.md`

## Working Style

- Favor libraries over custom builds when the library already solves most of the problem.
- Keep implementations small and observable.
- Add timeouts and error handling for every external dependency.
- Preserve demo quality. If a live path is fragile, provide a recordable fallback.
