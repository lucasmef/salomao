# Arquitetura Atual

## Principios

- `vps-first`: toda operacao oficial roda no VPS da KingHost
- `dois ambientes`: `dev` para homologacao e `prod` para producao
- `backend serving frontend`: o backend entrega a API e o frontend compilado
- `postgresql como banco oficial`: producao e homologacao usam PostgreSQL
- `seguranca de borda`: acesso publico via `Nginx`, `HTTPS`, `systemd`, `UFW` e `fail2ban`

## Topologia

### Ambiente dev

- checkout: `/srv/salomao/dev/app`
- backend: `salomao-dev.service`
- healthcheck: `http://127.0.0.1:8101/api/v1/health`
- banco: `gestor_financeiro_dev`
- uso: homologacao e validacao antes da publicacao

### Ambiente prod

- checkout: `/srv/salomao/prod/app`
- backend: `salomao-prod.service`
- healthcheck: `http://127.0.0.1:8100/api/v1/health`
- banco: `gestor_financeiro_prod`
- origem publica: `https://salomao.example.invalid`

## Aplicacao

- frontend: `React + Vite`
- backend: `FastAPI + SQLAlchemy`
- frontend compilado: `frontend/dist`
- entrega web: [backend/app/main.py](/C:/Users/lucas/OneDrive/Documentos/GESTOR%20FINANCEIRO/backend/app/main.py)

## Infraestrutura

- proxy reverso: `Nginx`
- processo: `systemd`
- firewall: `UFW`
- protecao de bans: `fail2ban`
- banco: `PostgreSQL`

## Configuracao

Cada checkout do VPS precisa de seu proprio `backend/.env`.

Arquivos de referencia versionados:

- `backend/.env.example`
- `backend/.env.dev.example`
- `backend/.env.prod.example`

Chaves minimas:

- `APP_MODE=server`
- `DATABASE_URL=postgresql+psycopg://...`
- `SESSION_SECRET=...`
- `FIELD_ENCRYPTION_KEY=...`
- `PUBLIC_ORIGIN=https://salomao.example.invalid`

## Operacao

Deploys padronizados:

- `./scripts/deploy-dev.sh`
- `./scripts/deploy-prod.sh`

Auditoria operacional:

- `./scripts/check-prod.sh`
