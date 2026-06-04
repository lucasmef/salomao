# Desenvolvimento local com SQLite

## Escopo

Este runbook registra a decisao de usar SQLite apenas no desenvolvimento local leve.

- Local do desenvolvedor: SQLite em arquivo local.
- Dev no VPS: PostgreSQL existente, sem alteracao.
- Prod no VPS: PostgreSQL existente, sem alteracao.

O SQLite local serve para abrir a aplicacao, testar fluxos de interface, desenvolver endpoints e trabalhar sem Docker ou PostgreSQL instalado. Validacoes finais de comportamento sensivel ainda devem considerar o PostgreSQL dos ambientes oficiais.

## Arquivo de ambiente local

Copie o exemplo versionado e ajuste os valores locais:

```powershell
Copy-Item -LiteralPath "backend/env.local.example" -Destination "backend/.env.local"
```

O arquivo `backend/.env.local` nao e versionado. Ele deve conter apenas valores ficticios ou segredos gerados localmente:

```env
APP_MODE=local
DATABASE_URL=sqlite:///./.runtime/gestor_financeiro.dev.sqlite3
BOOTSTRAP_ADMIN_EMAIL=admin@example.invalid
BOOTSTRAP_ADMIN_PASSWORD=<LOCAL_DEV_PASSWORD>
SESSION_SECRET=<LOCAL_SESSION_SECRET>
FIELD_ENCRYPTION_KEY=<LOCAL_FIELD_ENCRYPTION_KEY>
PUBLIC_ORIGIN=http://127.0.0.1:8000
```

Use `SALOMAO_ENV_FILE` para apontar o backend para esse arquivo quando quiser rodar localmente:

```powershell
cd backend
$env:SALOMAO_ENV_FILE = ".env.local"
```

Se o terminal ja tiver `APP_MODE`, `DATABASE_URL` ou outras variaveis do backend definidas, elas tem precedencia sobre o arquivo. Nesse caso, feche o terminal, limpe as variaveis conflitantes ou sobrescreva explicitamente para o fluxo local.

Nao reutilize arquivos de ambiente do VPS e nao versionar `backend/.env.local`.

## Criar ou atualizar o banco local

```powershell
cd backend
uv sync --extra dev
$env:SALOMAO_ENV_FILE = ".env.local"
$env:PYTHONPATH = "."
uv run python scripts/init_local_sqlite.py
```

O arquivo esperado sera criado em:

```text
backend/.runtime/gestor_financeiro.dev.sqlite3
```

## Popular dados ficticios

Depois de criar o banco local, rode o seed demo para abrir dashboards, fluxo de caixa, boletos, conciliacao e listas Linx com dados descartaveis:

```powershell
cd backend
$env:SALOMAO_ENV_FILE = ".env.local"
$env:PYTHONPATH = "."
uv run python scripts/seed_local_demo.py
```

O seed recria apenas os dados ficticios marcados como `local_demo_seed`. Ele nao deve ser usado em `APP_MODE=server` e nao substitui validacao com PostgreSQL.

## Rodar o backend

```powershell
cd backend
$env:SALOMAO_ENV_FILE = ".env.local"
$env:PYTHONPATH = "."
uv run uvicorn app.main:app --reload
```

Na primeira inicializacao com banco vazio, o bootstrap admin usa `BOOTSTRAP_ADMIN_EMAIL` e `BOOTSTRAP_ADMIN_PASSWORD`. Depois de validar o acesso local, mantenha esses valores apenas no arquivo local nao versionado.

## Rodar o frontend

Em outro terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Se o frontend precisar apontar para uma API especifica, use somente variaveis locais nao versionadas conforme o padrao existente do projeto.

## Reset local

Para reconstruir o banco local do zero, pare o backend e remova apenas o arquivo SQLite local:

```powershell
Remove-Item -LiteralPath "backend/.runtime/gestor_financeiro.dev.sqlite3"
```

Depois rode novamente:

```powershell
cd backend
$env:SALOMAO_ENV_FILE = ".env.local"
$env:PYTHONPATH = "."
uv run python scripts/init_local_sqlite.py
uv run python scripts/seed_local_demo.py
```

O seed local deve conter apenas dados ficticios.

## Limites do SQLite local

SQLite nao substitui o PostgreSQL dos ambientes oficiais. Antes de entregar alteracoes em areas sensiveis, valide com os testes relevantes e considere homologar no dev VPS quando houver risco em:

- migrations e tipos de banco;
- queries SQL complexas, agregacoes, datas e `GROUP BY`;
- concorrencia, locks e transacoes;
- relatorios financeiros, conciliacao, boletos, Banco Inter, Linx e cache analitico.

## Validacao recomendada

Para mudancas comuns:

```powershell
cd backend
$env:PYTHONPATH = "."
uv run pytest
uv run ruff check <arquivos-python-alterados>
```

Para mudancas de frontend:

```powershell
cd frontend
npm run typecheck
npm run build
```

Para documentacao, configuracao ou operacao:

```powershell
python scripts/security_scan.py
```

## Politica operacional preservada

- O banco local SQLite e descartavel e nao deve ser usado como fonte de dados real.
- Arquivos `.sqlite3`, `.db`, backups e `.env` reais nao devem entrar no git.
- Dev VPS e prod VPS continuam usando PostgreSQL.
- Deploy e producao continuam pelo fluxo oficial de GitHub Actions e aprovacao manual quando aplicavel.
