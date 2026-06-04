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

---

## BuilderFlow

This repository uses BuilderFlow for AI-assisted development.

When the user says `Use BuilderFlow`, Codex must use the `builderflow` skill.

BuilderFlow is the primary process for planning and executing tasks. It owns task classification, Grill Gate questions, living specs, ADR handling, validation reporting, and final summaries.

Project-specific skills, if present, are companion skills for domain-specific rules only. Use them when a task touches product data, sensitive modules, architecture, security, integrations, or repository-specific conventions.

Default workflow:

1. Read repository context before acting.
2. Work one feature or task at a time.
3. Create or update one living spec in `specs/`.
4. Ask questions only after reading docs and code.
5. Prefer small, reversible, verifiable changes.
6. Register ADRs only for architectural or hard-to-reverse decisions.
7. Update the living spec before ending the task.
8. For frontend-impacting work, complete local browser validation and save screenshots in `specs/artifacts/<spec-slug>/` before marking the task done. When a fix has visual impact, also save a proof copy in the global folder `G:\Meu Drive\.agentes`, named `gestor-financeiro-<screen>-<YYYY-MM-DD>[-n].png`.

Important files:

- `docs/CONTEXT.md` - current project context
- `docs/ADR.md` - durable architectural decisions
- `.claude/skills/builderflow/SKILL.md` - BuilderFlow skill (Claude Code)
- `.agents/skills/builderflow/SKILL.md` - BuilderFlow skill (Codex / other agents)
- `specs/` - one living spec per task or feature
- `specs/artifacts/` - screenshots and visual validation evidence grouped by spec slug

Do not create separate PRD, TASKS, STATUS, HANDOFF, or NOTES files unless the user explicitly asks.
