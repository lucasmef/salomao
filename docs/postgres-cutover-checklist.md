# Operacao Atual do PostgreSQL

A migracao para PostgreSQL ja foi concluida.

Este documento existe apenas para registrar a operacao atual e evitar que processos futuros sigam o fluxo antigo de desktop/SQLite.

## Estado oficial

- `dev` no VPS usa `gestor_financeiro_dev`
- `prod` no VPS usa `gestor_financeiro_prod`
- o banco oficial do sistema em operacao e PostgreSQL
- deploy oficial existe apenas no VPS da KingHost

## Para atualizar schema

```bash
cd /srv/salomao/prod/app/backend
./.venv/bin/python -m alembic upgrade head
```

## Para publicar codigo

```bash
cd /srv/salomao/prod/app
./scripts/deploy-prod.sh
```

## Para homologar antes

```bash
cd /srv/salomao/dev/app
./scripts/deploy-dev.sh
```

## Para auditar producao

```bash
cd /srv/salomao/prod/app
./scripts/check-prod.sh
```
