# Project Context

This file stores durable project context for Codex and BuilderFlow.

Update this file with stable facts about the product, stack, workflows, commands, conventions, and sensitive areas.

## Product

Salomão é um backoffice financeiro para uma operação comercial brasileira. Centraliza lançamentos financeiros, contas e categorias, conciliação bancária, cobrança e boletos, relatórios de caixa/resultados, planejamento de compras e integrações com Linx e Banco Inter.

O sistema trata dados financeiros, pessoais e credenciais de integrações. Mudanças nesses domínios exigem escopo pequeno, testes proporcionais e nunca usam dados reais sem autorização explícita.

## User workflow

- A rodada de manutenção pode conter qualquer quantidade de IDs de intake (`SAL-*`). O executor recebe e analisa a rodada completa antes de alterar arquivos.
- BuilderFlow é o processo primário: carrega contexto real, executa Grill Gate, decide quantas living specs são necessárias, agrupa ou separa por domínio, risco e dependências, define a ordem técnica e executa cada spec sequencialmente.
- A rastreabilidade é individual e obrigatória: `SAL-ID → living spec → alteração ou achado → validação → evidência`.
- Grill Me só ocorre quando documentação, contexto, ADRs, specs, código, testes, padrões e skills não resolvem uma decisão material. Itens independentes continuam enquanto houver resposta pendente.
- O usuário revisa depois; não há deploy, promoção a `main` ou operação mutável na VPS sem autorização explícita.

## Agent workflow roles

- `builderflow` is the primary process skill. It governs task classification, Grill Gate, living specs in `specs/`, ADR handling, validation reporting, and final summaries.
- Project-specific skills, if present, are companion domain-rules skills. Use them for project-specific rules around data, sensitive modules, architecture, security, integrations, and repository conventions.
- Do not treat domain-rules skills as competing planning workflows.
- Frontend-impacting BuilderFlow tasks require temporary local server validation, browser testing, screenshots, and server shutdown before the task can be marked done.

## Development workflow

- `dev`: branch normal de desenvolvimento e homologação.
- `main`: linha de produção, com promoção e deploy manuais por operador humano.
- A aplicação oficial é executada no VPS: backend FastAPI serve o frontend Vite compilado; produção é pública via Nginx/HTTPS e homologação é privada via Tailscale.
- Workflows GitHub Actions fazem a sincronização e preparação operacional no runner self-hosted; agentes não fazem deploy por SSH nem disparam deploy de produção.
- Configuração de runtime fica fora do repositório, normalmente em `../salomao-config/backend.env`; somente arquivos `.env.*.example` são versionados.

## Stack

- Backend: Python 3.12+, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, PostgreSQL/psycopg, Redis, pytest, ruff e uv.
- Frontend: React 19, TypeScript, React Router, Vite e npm.
- Segurança de borda representada: Nginx, TLS, systemd, UFW, fail2ban e Tailscale para acesso privado de dev/SSH.
- Integrações e domínios sensíveis: Banco Inter (mTLS/boletos/extratos), Linx (importação/sincronização), conciliação, compras, auditoria, cache e backups.

## Commands

Comandos descobertos:

- Backend install: `cd backend && uv sync --extra dev`
- Backend tests: `cd backend && PYTHONPATH=. uv run pytest <alvo>`
- Backend lint: `cd backend && uv run ruff check <arquivos-python-alterados>`
- Frontend install: `cd frontend && npm ci`
- Frontend typecheck: `cd frontend && npm run typecheck`
- Frontend build: `cd frontend && npm run build`
- Segurança do repositório: `python scripts/security_scan.py` (ou o Python fornecido por `uv` quando `python` não estiver no `PATH`)

## Frontend validation evidence

When a task changes user-facing frontend behavior, layout, navigation, styling, forms, interactive states, or any visible screen:

- run the local web app temporarily after implementation
- check for an existing server or occupied port before starting a new one
- record server command, port, PID/process, and shutdown result in the living spec
- manually test the affected screen or flow in the browser
- save screenshots under `specs/artifacts/<spec-slug>/`, com rota, viewport e cenário na spec; registrar before quando aplicável e after obrigatoriamente, para desktop e mobile quando afetados
- fazer a cópia global em `G:\Meu Drive\.agentes` com prefixo `gestor-financeiro-` quando o volume estiver disponível; registrar a indisponibilidade quando não estiver
- use ordered descriptive screenshot names, such as `01-today-list.png` or `02-editor-empty-state.png`
- reference screenshot paths in the living spec validation section
- stop every server, watcher, and child process started by the agent before final response

## Important conventions

- Não criar PRD, TASKS, STATUS, HANDOFF ou NOTES paralelos: a living spec é a fonte de planejamento, progresso, validação e próxima ação.
- Não incluir segredos, certificados, dumps, backups, dados de clientes, logs sensíveis ou evidências de deploy no Git.
- O scanner oficial de segredos e artefatos é `scripts/security_scan.py`; varreduras de dependência front-end são executadas no workflow `Security Checks`.
- O lint completo do repositório não é gate confiável por dívida legada; usar lint dirigido aos arquivos modificados.

## Sensitive areas

Document modules that require extra care, such as:

- autenticação, autorização, sessões, MFA e alertas de segurança
- cálculos financeiros, conciliação, cobranças, compras e regras de baixa
- importações, arquivos ZIP/XLSX/OFX, sincronizações Linx/Banco Inter e credenciais mTLS
- produção, pipelines, scripts de deploy, banco, backups, Redis e migrações
- dados de clientes, fornecedores, transações e toda evidência visual
