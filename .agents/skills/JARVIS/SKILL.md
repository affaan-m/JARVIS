```markdown
# JARVIS Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches you the core development patterns used in the JARVIS repository, a TypeScript codebase with no detected framework. You'll learn about file naming, import/export styles, commit conventions, testing patterns, and how to execute common workflows such as dependency updates.

## Coding Conventions

### File Naming
- **Style:** camelCase
- **Example:**  
  ```
  userProfile.ts
  apiClient.ts
  ```

### Import Style
- **Style:** Relative imports
- **Example:**
  ```typescript
  import { fetchData } from './apiClient';
  ```

### Export Style
- **Style:** Named exports
- **Example:**
  ```typescript
  // In userProfile.ts
  export function getUserProfile(id: string) { ... }
  ```

### Commit Messages
- **Type:** Conventional commits
- **Prefix:** `chore`
- **Average Length:** ~51 characters
- **Example:**
  ```
  chore: update dependency versions in package.json
  ```

## Workflows

### Dependency Update Workflow
**Trigger:** When you need to update project dependencies to the latest versions or resolve dependency audit failures.  
**Command:** `/update-dependencies`

1. Update dependency version(s) in `backend/pyproject.toml` or `frontend/package.json`.
2. Regenerate lockfiles:
    - For backend: `backend/uv.lock`
    - For frontend: `frontend/package-lock.json`
3. Commit changes to dependency files and lockfiles.
4. Push your changes and open a pull request if required.

**Files Involved:**
- `backend/pyproject.toml`
- `backend/uv.lock`
- `frontend/package.json`
- `frontend/package-lock.json`

**Example Commit:**
```
chore: bump frontend dependencies and update lockfile
```

## Testing Patterns

- **Framework:** Unknown (not detected)
- **File Pattern:** Test files use the `*.test.*` naming convention.
- **Example:**
  ```
  apiClient.test.ts
  ```
- **Typical Structure:**  
  Test files are placed alongside or near the code they test, following the camelCase naming convention.

## Commands

| Command              | Purpose                                                      |
|----------------------|--------------------------------------------------------------|
| /update-dependencies | Update backend and frontend dependencies and lockfiles        |
```