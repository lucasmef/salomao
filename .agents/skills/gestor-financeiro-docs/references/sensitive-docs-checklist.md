# Sensitive Docs Checklist

Use this checklist before creating or handing off README and documentation changes for Gestor Financeiro.

## Must Not Appear

- Real passwords, API keys, OAuth client secrets, session secrets, field encryption keys, webhook secrets, recovery codes, cookies, bearer tokens, private keys, certificate bodies, or PEM blocks.
- Real database URLs, usernames, passwords, hostnames, external IPs, Tailscale machine names, SSH usernames, private ports beyond documented localhost healthcheck examples, or exact production file paths that are not already intentionally public examples.
- Real customer, supplier, employee, bank, invoice, boleto, receivable, transaction, reconciliation, CPF/CNPJ, phone, address, email, Pix, barcode, linha digitavel, nosso numero, or account data.
- Raw logs, stack traces containing environment values, database dumps, backup names, screenshots with live data, generated deployment evidence, or security scan findings with exploitable details.
- Instructions that promote to `main`, deploy production, SSH into VPS, refresh production/dev databases, or disable safety controls unless the user explicitly requested an operational plan and the doc keeps approval gates manual.

## Safe Replacement Patterns

- Domains: use `example.invalid` or `salomao.example.invalid`.
- Emails: use `admin@example.invalid` or `user@example.invalid`.
- Secrets: use `<SECRET>`, `<SESSION_SECRET>`, `<FIELD_ENCRYPTION_KEY>`, or `...`.
- Database URLs: use `postgresql+psycopg://user:password@host:5432/dbname`.
- Commits and releases: use `<SHA>` or `<TAG>`.
- Services: use documented generic names such as `salomao-dev.service` and `salomao-prod.service` only when already part of project docs.
- Local healthchecks: localhost examples are acceptable when they match repository docs, such as `http://127.0.0.1:8101/api/v1/health`.

## Review Pass

1. Search changed docs for risky tokens: `SECRET`, `PASSWORD`, `TOKEN`, `KEY`, `PEM`, `DATABASE_URL`, `COOKIE`, `CPF`, `CNPJ`, `INTER`, `LINX`, `prod`, `backup`, `dump`, `ssh`, `tailscale`, `nginx`, `systemd`.
2. Verify each match is either a placeholder, a public-safe architectural reference, or required operational context.
3. Confirm `.env` examples contain placeholders only and do not imply real defaults.
4. Confirm deployment and database-refresh text preserves manual approval for production and does not instruct Codex to operate the VPS directly.
5. Confirm commands match `AGENTS.md` and do not include destructive operations.
6. Prefer running `python scripts/security_scan.py` before final handoff when documentation touches config, deploy, security, or operations.
