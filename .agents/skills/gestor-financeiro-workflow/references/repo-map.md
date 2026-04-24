# Gestor Financeiro Repo Map

## Subsystems

- `backend/app/api/routes`: FastAPI route handlers.
- `backend/app/schemas`: Pydantic request and response schemas.
- `backend/app/services`: business logic, integrations, cache, reports and financial operations.
- `backend/app/db/models`: SQLAlchemy models.
- `backend/alembic/versions`: schema migrations.
- `backend/tests`: pytest regression and service/API tests.
- `frontend/src/pages`: route-level React screens.
- `frontend/src/components`: shared UI components.
- `frontend/src/lib/api.ts`: frontend API client.
- `scripts`: VPS operations, deploy helpers, security scan and database maintenance.
- `.github/workflows`: CI/CD, deployment and operational workflows.

## Validation Selection

- Backend-only logic: run `uv run ruff check <touched-python-files>` and targeted `PYTHONPATH=. uv run pytest <test-file>` from `backend`.
- Financial, cache, security or integration logic: prefer full backend pytest when feasible.
- Frontend-only UI/type changes: run `npm run typecheck` and `npm run build` from `frontend`.
- Workflow, deploy or secret-handling changes: run `python scripts/security_scan.py` from the repo root and inspect the related workflow/script.
- Full-stack API shape changes: run backend tests plus frontend typecheck/build.

## Operational Defaults

- Work on `dev` unless the user explicitly asks otherwise.
- Deploy dev/prod through GitHub Actions, not local direct server commands.
- Keep production promotion and production deploy manual.
- Keep runtime configuration outside the repository; only example `.env` files are versioned.
