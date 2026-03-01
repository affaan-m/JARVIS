#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────
# SPECTER Agent Swarm Launcher
# Creates git worktrees + tmux session with parallel Claude agents
# ─────────────────────────────────────────────────────────────

REPO_ROOT="/Users/affoon/Documents/GitHub/YC_hackathon"
WORKTREE_BASE="${REPO_ROOT}/.claude/worktrees"
SESSION="specter-swarm"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${GREEN}[SWARM]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# ─────────────────────────────────────────────────────────────
# Agent definitions: name | branch | prompt
# ─────────────────────────────────────────────────────────────
declare -a AGENT_NAMES=(
  "backend-tests"
  "frontend-tests"
  "convex-linkage"
  "adapter-contracts"
)

declare -a AGENT_BRANCHES=(
  "codex/backend-tests-coverage"
  "codex/frontend-test-harness"
  "codex/convex-proof-of-life"
  "codex/adapter-contracts"
)

# Agent prompts (heredoc-safe, no single quotes inside)
PROMPT_BACKEND_TESTS=$(cat <<'PROMPT'
You are Agent 1: Backend Tests + Coverage.

Your mission: Expand backend test surface and add coverage enforcement.

Files to focus on:
- backend/main.py
- backend/capture/service.py
- backend/config.py
- backend/tasks.py
- backend/tests/

Tasks (in order):
1. Run `uv sync --extra dev` to ensure deps are installed
2. Add pytest-cov to dev dependencies in pyproject.toml
3. Add tests for /api/services endpoint
4. Add tests for /api/capture including upload handling
5. Add tests for settings parsing and service flag behavior
6. Add a small integration-style test that exercises capture -> response payload
7. Add a pytest.ini or pyproject.toml section to enforce minimum coverage (e.g. 70%)
8. Run `uv run pytest --cov=. --cov-report=term-missing` and verify all pass
9. Commit your changes to this branch with a clear message

Definition of done:
- `uv run pytest` passes
- Coverage is reported
- Coverage threshold is enforced

IMPORTANT: Work only within the backend/ directory. Do not touch frontend code.
PROMPT
)

PROMPT_FRONTEND_TESTS=$(cat <<'PROMPT'
You are Agent 2: Frontend Tests.

Your mission: Add Vitest + React Testing Library and create component tests.

Files to focus on:
- frontend/package.json
- frontend/src/app/page.tsx
- frontend/src/components/*
- Create: frontend/vitest.config.ts
- Create: frontend/src/**/*.test.tsx

Tasks (in order):
1. cd frontend && npm install
2. Add vitest, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, jsdom as dev dependencies
3. Create vitest.config.ts with jsdom environment
4. Add "test" script to package.json
5. Test Corkboard render with demo data
6. Test DossierView open/close behavior
7. Test LiveFeed click behavior
8. Test home page selected-person flow
9. Run tests and verify all pass
10. Commit your changes to this branch

Definition of done:
- `npm test` exists and passes
- Component tests run successfully
- No UI-only regressions require manual detection

IMPORTANT: Work only within the frontend/ directory. Do not touch backend code.
PROMPT
)

PROMPT_CONVEX=$(cat <<'PROMPT'
You are Agent 3: Convex Linkage.

Your mission: Replace demo-only data path with real Convex realtime plumbing.

Files to focus on:
- frontend/convex/*
- frontend/src/app/ConvexClientProvider.tsx
- frontend/src/app/page.tsx
- .env.example (if needed)

Tasks (in order):
1. Review existing Convex schema and config in frontend/convex/
2. Ensure Convex codegen is working (npx convex dev --once or similar)
3. Add a proof-of-life mutation that inserts a dummy person record
4. Add a corresponding query that reads person records
5. Wire the homepage to prefer live Convex data when configured
6. Keep demo fallback data if Convex is not configured
7. Test that the page works both with and without live Convex config
8. Commit your changes to this branch

Definition of done:
- One real person record can be inserted and rendered
- Page works with and without live Convex config

IMPORTANT: Focus on Convex integration. Coordinate with frontend but do not break existing components.
PROMPT
)

PROMPT_ADAPTERS=$(cat <<'PROMPT'
You are Agent 4: Service Adapter Contracts.

Your mission: Build narrow adapter interfaces for live integrations.

Files to focus on:
- backend/db/convex_client.py
- backend/enrichment/exa_client.py
- backend/observability/laminar.py
- Create: backend/identification/*.py
- Create: backend/synthesis/*.py

Tasks (in order):
1. Review existing adapter code in backend/db/, backend/enrichment/, backend/observability/
2. Define typed adapter interfaces for each service (Protocol classes or ABCs)
3. Add typed request/response payloads (Pydantic models) for each adapter
4. Add fixture-based tests for adapter request/response shaping
5. Add environment validation for each service (check required env vars)
6. Ensure all live calls are behind injectable clients (dependency injection)
7. Run ruff check and pytest to verify
8. Commit your changes to this branch

Definition of done:
- Adapters are testable with mocks
- No service integration is hardcoded directly into routes
- All adapter tests pass

IMPORTANT: Work only within the backend/ directory. Focus on clean contracts.
PROMPT
)

declare -a AGENT_PROMPTS=(
  "$PROMPT_BACKEND_TESTS"
  "$PROMPT_FRONTEND_TESTS"
  "$PROMPT_CONVEX"
  "$PROMPT_ADAPTERS"
)

# ─────────────────────────────────────────────────────────────
# Step 1: Create worktrees
# ─────────────────────────────────────────────────────────────
log "Creating worktree directory..."
mkdir -p "$WORKTREE_BASE"

cd "$REPO_ROOT"

for i in "${!AGENT_NAMES[@]}"; do
  name="${AGENT_NAMES[$i]}"
  branch="${AGENT_BRANCHES[$i]}"
  wt_path="${WORKTREE_BASE}/${name}"

  if [ -d "$wt_path" ]; then
    warn "Worktree ${name} already exists, removing..."
    git worktree remove "$wt_path" --force 2>/dev/null || true
  fi

  log "Creating worktree: ${name} -> ${branch}"
  # Create branch from main if it doesn't exist
  git branch "$branch" main 2>/dev/null || true
  git worktree add "$wt_path" "$branch"
done

log "All worktrees created:"
git worktree list

# ─────────────────────────────────────────────────────────────
# Step 2: Kill existing tmux session if present
# ─────────────────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
  warn "Killing existing tmux session: ${SESSION}"
  tmux kill-session -t "$SESSION"
fi

# ─────────────────────────────────────────────────────────────
# Step 3: Create tmux session with agent windows
# ─────────────────────────────────────────────────────────────
log "Creating tmux session: ${SESSION}"

# Create session with first agent window
tmux new-session -d -s "$SESSION" -n "${AGENT_NAMES[0]}" -c "${WORKTREE_BASE}/${AGENT_NAMES[0]}"

# Create remaining agent windows
for i in $(seq 1 $((${#AGENT_NAMES[@]} - 1))); do
  name="${AGENT_NAMES[$i]}"
  tmux new-window -t "$SESSION" -n "$name" -c "${WORKTREE_BASE}/${name}"
done

# ─────────────────────────────────────────────────────────────
# Step 4: Create monitoring windows
# ─────────────────────────────────────────────────────────────
log "Creating monitoring windows..."

# Backend monitor window
tmux new-window -t "$SESSION" -n "backend-logs" -c "${REPO_ROOT}/backend"

# Frontend monitor window
tmux new-window -t "$SESSION" -n "frontend-logs" -c "${REPO_ROOT}/frontend"

# ─────────────────────────────────────────────────────────────
# Step 5: Launch Claude agents in each worktree window
# ─────────────────────────────────────────────────────────────
log "Launching Claude agents..."

for i in "${!AGENT_NAMES[@]}"; do
  name="${AGENT_NAMES[$i]}"
  prompt="${AGENT_PROMPTS[$i]}"
  wt_path="${WORKTREE_BASE}/${name}"

  log "  -> Agent: ${name} in ${wt_path}"

  # Write prompt to a temp file to avoid quoting issues
  prompt_file="${WORKTREE_BASE}/${name}/.agent-prompt.txt"
  echo "$prompt" > "$prompt_file"

  # Launch claude in the agent window with the prompt
  tmux send-keys -t "${SESSION}:${name}" \
    "cd ${wt_path} && claude --dangerously-skip-permissions -p \"\$(cat ${prompt_file})\"" Enter
done

# ─────────────────────────────────────────────────────────────
# Step 6: Set up monitoring in log windows
# ─────────────────────────────────────────────────────────────
log "Setting up monitoring..."

# Backend logs: watch pytest output and uvicorn if running
tmux send-keys -t "${SESSION}:backend-logs" \
  "echo '=== BACKEND MONITOR ===' && echo 'Watching backend for changes...' && cd ${REPO_ROOT}/backend && watch -n 5 'echo \"--- Backend Status ---\" && git -C ${REPO_ROOT} worktree list && echo && echo \"--- Recent Backend Commits ---\" && for b in codex/backend-tests-coverage codex/adapter-contracts; do echo \"[\$b]\" && git log \$b --oneline -3 2>/dev/null || echo \"  (no commits yet)\"; echo; done'" Enter

# Frontend logs: watch npm output
tmux send-keys -t "${SESSION}:frontend-logs" \
  "echo '=== FRONTEND MONITOR ===' && echo 'Watching frontend for changes...' && cd ${REPO_ROOT}/frontend && watch -n 5 'echo \"--- Frontend Status ---\" && git -C ${REPO_ROOT} worktree list && echo && echo \"--- Recent Frontend Commits ---\" && for b in codex/frontend-test-harness codex/convex-proof-of-life; do echo \"[\$b]\" && git log \$b --oneline -3 2>/dev/null || echo \"  (no commits yet)\"; echo; done'" Enter

# ─────────────────────────────────────────────────────────────
# Step 7: Create a dashboard window with all panes
# ─────────────────────────────────────────────────────────────
log "Creating dashboard overview..."
tmux new-window -t "$SESSION" -n "dashboard" -c "$REPO_ROOT"
tmux send-keys -t "${SESSION}:dashboard" \
  "watch -n 10 'echo \"========== SPECTER SWARM DASHBOARD ==========\"; echo; git worktree list; echo; echo \"--- Branch Status ---\"; for b in codex/backend-tests-coverage codex/frontend-test-harness codex/convex-proof-of-life codex/adapter-contracts; do commits=\$(git log \$b --oneline 2>/dev/null | head -5); if [ -n \"\$commits\" ]; then echo \"[\$b]\"; echo \"\$commits\"; else echo \"[\$b] (no new commits)\"; fi; echo; done; echo \"========================================\"'" Enter

# ─────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  SPECTER Agent Swarm is LIVE${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Session:    ${YELLOW}${SESSION}${NC}"
echo -e "  Agents:     ${GREEN}4 Claude instances${NC}"
echo -e "  Worktrees:  ${GREEN}4 isolated branches${NC}"
echo -e "  Monitors:   ${GREEN}2 log streams + 1 dashboard${NC}"
echo ""
echo -e "  ${CYAN}Windows:${NC}"
echo -e "    0: ${YELLOW}backend-tests${NC}     -> codex/backend-tests-coverage"
echo -e "    1: ${YELLOW}frontend-tests${NC}    -> codex/frontend-test-harness"
echo -e "    2: ${YELLOW}convex-linkage${NC}    -> codex/convex-proof-of-life"
echo -e "    3: ${YELLOW}adapter-contracts${NC} -> codex/adapter-contracts"
echo -e "    4: ${YELLOW}backend-logs${NC}      -> Backend monitoring"
echo -e "    5: ${YELLOW}frontend-logs${NC}     -> Frontend monitoring"
echo -e "    6: ${YELLOW}dashboard${NC}         -> Branch commit overview"
echo ""
echo -e "  ${CYAN}Attach:${NC}  tmux attach -t ${SESSION}"
echo -e "  ${CYAN}Switch:${NC}  Ctrl+B then window number (0-6)"
echo -e "  ${CYAN}Kill:${NC}    tmux kill-session -t ${SESSION}"
echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
