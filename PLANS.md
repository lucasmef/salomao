# Planning Template

Use this template before changing sensitive areas: database migrations, security, deploy workflows, Banco Inter integration, cache/analytics, financial calculations, reconciliation, purchases, boletos, or production operations.

## Required Plan

1. State the goal and the user-visible success criteria.
2. Identify touched subsystems: backend, frontend, database, CI/CD, scripts, docs, or server operations.
3. List the files or modules likely to change.
4. Describe data flow and compatibility impact, including migrations, existing records, cache invalidation, and external APIs.
5. Define failure modes and rollback path.
6. Define validation: unit tests, integration tests, typecheck/build, security scan, or manual verification.

## Area-Specific Checks

- Database: include Alembic migration direction, downgrade expectations if relevant, and whether existing data needs backfill.
- Security: verify secrets stay outside git, preserve MFA/session/rate-limit guarantees, and run `python scripts/security_scan.py`.
- Deploy: keep prod manual, use GitHub Actions for deploy, and do not run local VPS deploy commands unless explicitly requested.
- Banco Inter: cover sandbox vs production behavior, mTLS credentials, idempotency, pagination, deduplication, and error handling.
- Cache/analytics: cover Redis live cache, persisted monthly snapshots, invalidation triggers, and rebuild behavior.
- Financial logic: cover sign conventions, dates, filters, company context, rounding, and regression tests.

## Handoff Format

End the plan with:

- Implementation steps in execution order.
- Test plan with exact commands.
- Assumptions and out-of-scope items.
- Production or rollout notes when applicable.
