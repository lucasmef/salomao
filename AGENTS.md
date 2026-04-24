# Agent Instructions

## Project Shape

- Work from the repository root unless a command explicitly says otherwise.
- Backend lives in `backend/`: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, pytest and ruff.
- Frontend lives in `frontend/`: React, TypeScript, Vite and static build served by the backend.
- Operational scripts live in `scripts/`; deployment and server checks are VPS-oriented.
- Architecture and deployment context live in `docs/`, especially `docs/architecture.md` and `docs/deploy-vps.md`.

## Default Commands

- Backend install/sync: `cd backend; uv sync --extra dev`
- Backend tests: `cd backend; $env:PYTHONPATH='.'; uv run pytest` on PowerShell, or `cd backend && PYTHONPATH=. uv run pytest` on bash.
- Backend lint for touched Python files: `cd backend; uv run ruff check <files>`
- Frontend install: `cd frontend; npm ci`
- Frontend typecheck: `cd frontend; npm run typecheck`
- Frontend build: `cd frontend; npm run build`
- Repository security scan: `python scripts/security_scan.py`

Run the smallest relevant checks during development. Before handing off broad changes, prefer running backend tests, ruff on touched Python files, and frontend typecheck/build when the touched area could affect them. Full-repo `ruff check .` is not yet a reliable gate because the repository has legacy lint debt.

## Operating Rules

- Treat `dev` as the normal working and homologation branch.
- Do not deploy directly to the VPS from a local session. Normal deploy happens through GitHub Actions.
- Do not promote to `main`, push production changes, or trigger production deploy unless the user explicitly requests it in that turn.
- Keep production manual: Codex may prepare changes and explain the production path, but should not execute it by default.
- Do not commit secrets, runtime databases, logs, backups, certificates, `.env` files other than examples, or generated deployment evidence.
- Preserve user changes in a dirty worktree. Never reset, checkout, or delete unrelated changes without explicit approval.

## Implementation Guidance

- For backend API changes, keep route schemas, service logic, models, and tests aligned. Add Alembic migrations for schema changes.
- For financial calculations, reports, cache, reconciliation, purchases, boletos, and Banco Inter flows, add or update tests that lock the business behavior.
- For frontend changes, preserve the existing visual system and shared components unless the task explicitly asks for redesign.
- For deployment, database refresh, sanitization, or security changes, read `PLANS.md` first and produce a plan before editing.
- For recurring project workflow questions, use `$gestor-financeiro-workflow` when available.

## Done Criteria

- The changed behavior is covered by a targeted test or an explicit reason is given for not adding one.
- Relevant validation commands were run and their result is reported.
- Any skipped validation is called out with the reason.
- Operational or security-sensitive changes include rollback or failure considerations.
