---
name: dependency-update-workflow
description: Workflow command scaffold for dependency-update-workflow in JARVIS.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /dependency-update-workflow

Use this workflow when working on **dependency-update-workflow** in `JARVIS`.

## Goal

Updates backend and frontend dependencies to newer versions and updates lockfiles to ensure consistent builds.

## Common Files

- `backend/pyproject.toml`
- `backend/uv.lock`
- `frontend/package.json`
- `frontend/package-lock.json`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Update dependency version(s) in backend/pyproject.toml or frontend/package.json
- Regenerate lockfiles (backend/uv.lock, frontend/package-lock.json)
- Commit changes to dependency files and lockfiles

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.