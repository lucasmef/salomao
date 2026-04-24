---
name: gestor-financeiro-workflow
description: Project workflow for the Gestor Financeiro repository. Use when Codex needs to investigate bugs, change FastAPI endpoints, update React/Vite screens, alter reports/cache/analytics, work on Banco Inter integration, review deployment or security behavior, add tests, or prepare safe implementation plans for this project.
---

# Gestor Financeiro Workflow

## Core Workflow

1. Start from repo truth: read `AGENTS.md`, then inspect the touched backend, frontend, docs, workflow, or script files before deciding.
2. For sensitive work, read `PLANS.md` and produce a compact plan before editing.
3. Keep changes scoped to the requested behavior and preserve existing operational policy: `dev` is the normal work branch, production remains manual, and Codex does not deploy directly to the VPS by default.
4. Add or update tests when changing financial behavior, security, cache/analytics, Banco Inter flows, reconciliation, purchases, reports, or backend services.
5. Run the smallest relevant validation commands and report skipped checks explicitly.

## Task Guidance

- FastAPI endpoint: align route, schema, service logic, tests, and API client usage in the frontend when applicable.
- Database change: add an Alembic migration, consider existing data/backfill, and test the affected service behavior.
- React/Vite screen: preserve existing shared components and visual system unless the user asks for redesign.
- Report/cache/analytics change: account for Redis live cache, persisted monthly snapshots, invalidation, and rebuild behavior.
- Banco Inter change: handle sandbox/production differences, mTLS credentials, pagination, deduplication, idempotency, and API errors.
- Security/deploy change: keep secrets out of git, keep production manual, and run the security scan.

## Validation Commands

- Backend install: `cd backend; uv sync --extra dev`
- Backend tests: `cd backend; $env:PYTHONPATH='.'; uv run pytest` on PowerShell, or `cd backend && PYTHONPATH=. uv run pytest` on bash.
- Backend lint: `cd backend; uv run ruff check <touched-python-files>`
- Frontend install: `cd frontend; npm ci`
- Frontend typecheck: `cd frontend; npm run typecheck`
- Frontend build: `cd frontend; npm run build`
- Security scan: `python scripts/security_scan.py`

Full-repo `ruff check .` currently exposes legacy lint debt and should be treated as technical-debt discovery, not as the default pass/fail gate.

## References

- Read `references/repo-map.md` for a compact map of subsystems and validation choices.
