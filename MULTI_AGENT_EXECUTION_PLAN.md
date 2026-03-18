# JARVIS Multi-Agent Execution Plan

## Purpose

This plan is for parallel execution across multiple agents or terminals. It reflects the repo as it exists now, not the original blank-slate task list.

## Current Verified State

- Private GitHub repo exists and `main` is clean.
- Backend scaffold exists:
  - `backend/main.py`
  - `backend/config.py`
  - `backend/tasks.py`
  - `backend/tests/test_health.py`
- Frontend scaffold exists:
  - `frontend/src/app/page.tsx`
  - `frontend/src/components/*`
  - `frontend/src/lib/demo-data.ts`
- GitHub automation exists:
  - `.github/workflows/ci.yml`
  - `.github/workflows/codeql.yml`
  - `.github/workflows/dependency-review.yml`
  - `.github/workflows/deploy.yml`
- Local verification status:
  - Frontend `lint`, `typecheck`, `build`: passing
  - Backend `ruff`, `pytest`: passing

## Reality Check

What exists is a solid scaffold, not a validated pipeline.

Missing or weak:

- Backend unit test depth
- Backend integration tests
- Frontend component tests
- End-to-end tests
- Coverage reporting and gates
- Real Convex linkage
- Real service integrations
- Data pipeline execution beyond stubs

## Hard Priorities

Do these in this order:

1. Expand test surface before adding too many live integrations.
2. Link Convex and replace demo-only frontend data with real query hooks.
3. Build the first real pipeline end-to-end:
   `capture -> queue -> identify stub -> person record -> board update`
4. Add service adapters behind narrow contracts.
5. Add e2e and eval loops before deeper research-agent work.

## Parallel Workstreams

### Workstream A: Backend Verification

Owner focus: backend API quality and test depth

Files:

- `backend/main.py`
- `backend/capture/service.py`
- `backend/config.py`
- `backend/tests/`
- `backend/pyproject.toml`

Tasks:

1. Add tests for `/api/services`.
2. Add tests for `/api/capture` including upload handling.
3. Add tests for settings parsing and service flag behavior.
4. Add `pytest-cov` and enforce a first backend coverage threshold.
5. Add a small integration-style test that exercises `capture -> response payload`.

Definition of done:

- `uv run pytest` passes
- coverage is reported in CI
- backend coverage threshold is enforced

### Workstream B: Frontend Verification

Owner focus: component tests and interaction stability

Files:

- `frontend/package.json`
- `frontend/src/app/page.tsx`
- `frontend/src/components/*`
- add `frontend/vitest.config.*`
- add `frontend/src/**/*.test.tsx`

Tasks:

1. Add Vitest + React Testing Library.
2. Test `Corkboard` render with demo data.
3. Test `DossierView` open/close behavior.
4. Test `LiveFeed` click behavior.
5. Test home page selected-person flow.

Definition of done:

- `npm test` exists
- component tests run in CI
- no UI-only regressions require manual detection

### Workstream C: Convex Linkage

Owner focus: replacing demo-only data path with real realtime plumbing

Files:

- `frontend/convex/*`
- `frontend/src/app/ConvexClientProvider.tsx`
- `frontend/src/app/page.tsx`
- possibly `.env.example`

Tasks:

1. Link a real Convex project.
2. Run codegen and keep generated artifacts consistent.
3. Add the proof-of-life mutation/query flow for one dummy person.
4. Switch the homepage to prefer live Convex data when configured.
5. Keep demo fallback data if Convex is not configured.

Definition of done:

- one real person record can be inserted and rendered
- page works with and without live Convex config
- `T04` in `TASKS.md` can be marked done

### Workstream D: CI/CD Hardening

Owner focus: branch protection quality and deploy readiness

Files:

- `.github/workflows/*`
- `.github/CODEOWNERS`
- maybe `README.md`

Tasks:

1. Add frontend test job once Workstream B lands.
2. Add backend coverage upload/reporting once Workstream A lands.
3. Add cache improvements if CI is slow.
4. Document required secrets for deploy workflow:
   - `VERCEL_TOKEN`
   - `VERCEL_ORG_ID`
   - `VERCEL_PROJECT_ID`
5. Optionally add a PR label or conventional-title check if noise becomes a problem.

Definition of done:

- CI reflects actual project quality gates
- deploy workflow is documented and ready once secrets are present

### Workstream E: Service Adapter Contracts

Owner focus: narrow seams for live integrations without letting external APIs infect the codebase

Files:

- `backend/db/convex_client.py`
- `backend/enrichment/exa_client.py`
- `backend/observability/laminar.py`
- add:
  - `backend/identification/*.py`
  - `backend/synthesis/*.py`

Tasks:

1. Expand adapter interfaces and typed payloads.
2. Add fixture-based tests for adapter request/response shaping.
3. Add environment validation for each service.
4. Keep all live calls behind injectable clients.

Definition of done:

- adapters are testable with mocks
- no service integration is hardcoded directly into routes

### Workstream F: First Real Pipeline

Owner focus: first end-to-end system slice

Files:

- `backend/capture/service.py`
- `backend/identification/*`
- `backend/db/*`
- `frontend/convex/*`

Target slice:

1. Upload media to `/api/capture`
2. Queue or stub a capture record
3. Create a person record from a deterministic identification stub
4. Surface that record to the frontend board

Definition of done:

- one happy path works end-to-end
- all external services can still be mocked
- there is at least one integration test and one e2e test for this slice

### Workstream G: End-to-End and Evals

Owner focus: confidence before demo work

Files to add:

- `frontend/playwright.config.ts`
- `frontend/e2e/*.spec.ts`
- `backend/tests/integration/*`
- `scripts/` for eval fixtures if needed

Tasks:

1. Add Playwright.
2. Add one smoke e2e:
   - load board
   - select person
   - open dossier
3. After Convex linkage, add one e2e with live data.
4. Add a minimal eval dataset for synthesis and enrichment fixtures.

Definition of done:

- one deterministic UI smoke path runs in CI
- one deterministic pipeline eval exists for backend work

## Recommended Agent Split Right Now

If you are actually running multiple agents, use this split:

### Agent 1: Backend Tests + Coverage

Do Workstream A first.

Immediate output:

- `pytest-cov`
- new backend tests
- CI coverage enforcement

### Agent 2: Frontend Tests

Do Workstream B.

Immediate output:

- Vitest setup
- first component tests
- CI test step for frontend

### Agent 3: Convex Integration

Do Workstream C.

Immediate output:

- linked Convex project
- live mutation/query proof of life
- page path that prefers live data over demo data

### Agent 4: Service Contract Layer

Do Workstream E in parallel while Agent 3 links Convex.

Immediate output:

- adapter interfaces
- mocks
- tests for request/response contracts

### Agent 5: First Pipeline Slice

Starts after Agent 3 and Agent 4 establish the minimum contracts.

Immediate output:

- first real capture-to-board path

### Agent 6: E2E + Eval

Starts after Agent 2 and Agent 5 have a stable path.

Immediate output:

- Playwright smoke test
- first integration/eval checks

## Branch Strategy

Do not pile all of this into one branch.

Suggested branches:

- `codex/backend-tests-coverage`
- `codex/frontend-test-harness`
- `codex/convex-proof-of-life`
- `codex/adapter-contracts`
- `codex/capture-first-pipeline`
- `codex/e2e-smoke`

## Merge Order

1. backend tests and coverage
2. frontend test harness
3. convex proof of life
4. adapter contracts
5. first pipeline slice
6. e2e smoke

## Commands To Keep Reusing

Frontend:

```bash
cd frontend
npm run lint
npm run typecheck
PATH=/Users/affoon/.nvm/versions/node/v20.19.5/bin:$PATH npm run build
```

Backend:

```bash
cd backend
uv sync --extra dev
uv run ruff check .
uv run pytest
```

## What Should Be True Before Building More Agents

These are the preconditions:

- backend coverage exists and is enforced
- frontend component tests exist
- Convex proof of life works
- one e2e smoke path exists

If those are not true, deeper Browser Use and research-agent work will produce a fast-growing, weakly validated codebase.

## The Next Single Best Move

If only one thing happens next, do this:

**Build the test harnesses first, then link Convex.**

That gives the project a safe base for all later service and pipeline work.
