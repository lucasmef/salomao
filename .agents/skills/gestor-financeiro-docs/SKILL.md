---
name: gestor-financeiro-docs
description: Create, rewrite, review, or maintain professional README and documentation for the Gestor Financeiro project. Use when Codex needs to update README.md, docs/*.md, technical architecture docs, deployment notes, operational runbooks, feature documentation, handoff documents, or public-facing project descriptions while preserving project truth and preventing exposure of secrets, production details, customer data, credentials, internal URLs, real hostnames, tokens, certificates, database dumps, logs, backups, or other sensitive information.
---

# Gestor Financeiro Docs

## Core Workflow

1. Read the target documentation file and the closest source of truth before editing. For broad project docs, start with `README.md`, `docs/architecture.md`, `docs/deploy-vps.md`, and relevant code paths named in the doc.
2. Establish the document audience: public portfolio, internal developer handoff, operations runbook, security/deploy note, or feature documentation.
3. Preserve factual accuracy. Prefer verified repository facts over aspirational claims; mark uncertain points as TODOs only when the user explicitly wants placeholders.
4. Remove or generalize sensitive details before writing. Read `references/sensitive-docs-checklist.md` whenever the doc mentions environment variables, deployment, bank integrations, customers, credentials, logs, backups, production, VPS, SSH, database refresh, or security controls.
5. Write concise professional Portuguese by default for this repository. Keep existing ASCII style unless the file already uses accents consistently.
6. Keep documentation actionable: include commands, file paths, validation steps, rollback/failure notes, and links only when they help the reader operate or maintain the system.
7. Run a final self-review for sensitivity, dead links, stale version claims, inconsistent branch/deploy policy, and commands that do not match `AGENTS.md`.

## Documentation Standards

- Use the current README tone: direct, technical, product-aware, and credible.
- Structure README-style docs around: project purpose, capabilities, architecture, stack, operation, configuration, tests, repository map, and responsibility boundaries.
- Structure runbooks around: scope, prerequisites, step-by-step procedure, validation, rollback, and known failure modes.
- Structure feature docs around: user workflow, data model or service boundaries, API/frontend touchpoints, permissions/security, tests, and operational impact.
- Prefer examples with placeholders such as `example.invalid`, `127.0.0.1`, `<SHA>`, `<SERVICE>`, and `<ENV_FILE>`.
- Do not invent support claims, compliance claims, security guarantees, uptime, or production status beyond what the repository supports.
- Do not include marketing exaggeration. Show engineering maturity through concrete architecture, tests, safety controls, and operational workflow.

## Project Facts To Preserve

- Backend: `backend/`, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, pytest, ruff.
- Frontend: `frontend/`, React, TypeScript, Vite, static build served by backend.
- Official branch policy: `dev` is normal work and homologation; production promotion to `main` is manual.
- Official deploy path: GitHub Actions to VPS; Codex does not deploy directly to the VPS by default.
- Runtime secrets stay outside the repository; version only `.env.example` style references.
- Important domains: finance, Banco Inter, Linx, reconciliation, boletos, purchases, analytics cache, MFA/auth, audit, and operational safety.

## Sensitive Information Rules

- Never publish real credentials, tokens, secrets, PEM blocks, cookies, session values, MFA recovery data, database URLs, private IP topology, customer records, bank account details, CPF/CNPJ, phone numbers, emails, invoices, boleto identifiers, logs, backups, dumps, certificates, or production-only paths.
- Generalize infrastructure details that could enable unauthorized access. Keep only enough detail for maintainers to understand the architecture.
- Replace real examples with safe placeholders and example domains.
- When documenting security, describe controls and expected behavior without exposing bypass details, exact alert payloads, or live operational evidence.
- If a requested doc requires sensitive values to be useful, create a template with placeholders and state where the real value should live outside git.

## Validation

- For doc-only edits, run `python scripts/security_scan.py` when practical, especially before handoff of README, deployment, security, environment, or operational docs.
- Check Markdown links manually or with repo search when the edit changes paths.
- Report any skipped validation and the reason.

## References

- Read `references/sensitive-docs-checklist.md` for the detailed redaction and review checklist.
