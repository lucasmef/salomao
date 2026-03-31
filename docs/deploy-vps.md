# Deploy no VPS da KingHost

Este projeto publica somente no VPS da KingHost.

Nao existe mais deploy local, empacotamento desktop ou fluxo operacional via executavel/atalhos.

## Ambientes oficiais

- `dev`: homologacao no VPS
- `prod`: producao no VPS

Checkouts esperados no servidor:

- `/srv/salomao/dev/app`
- `/srv/salomao/prod/app`

Servicos esperados:

- `salomao-dev.service`
- `salomao-prod.service`

## Regra para qualquer processo

Se um processo precisar fazer deploy, ele deve:

1. acessar o checkout correto no VPS
2. garantir `backend/.env` do ambiente
3. rodar o script padronizado do ambiente
4. validar o healthcheck
5. em producao, rodar tambem a auditoria rapida

## Arquivos de ambiente

O arquivo real de runtime e sempre `backend/.env` dentro do checkout do VPS.

Arquivos versionados de referencia:

- `backend/.env.example`
- `backend/.env.dev.example`
- `backend/.env.prod.example`

Configuracao minima:

```env
APP_MODE=server
DATABASE_URL=postgresql+psycopg://...
SESSION_SECRET=...
FIELD_ENCRYPTION_KEY=...
PUBLIC_ORIGIN=https://salomao.example.invalid
```

## Deploy de homologacao

No checkout `/srv/salomao/dev/app`:

```bash
./scripts/deploy-dev.sh
```

O script:

1. valida `backend/.env`
2. valida `APP_MODE=server`
3. valida `DATABASE_URL` PostgreSQL
4. roda `npm ci`
5. roda `npm run build`
6. roda `alembic upgrade head`
7. reinicia `salomao-dev.service`
8. testa `http://127.0.0.1:8101/api/v1/health`

## Deploy de producao

No checkout `/srv/salomao/prod/app`:

```bash
./scripts/deploy-prod.sh
```

O script:

1. valida `backend/.env`
2. valida `APP_MODE=server`
3. valida `DATABASE_URL` PostgreSQL
4. roda `npm ci`
5. roda `npm run build`
6. roda `alembic upgrade head`
7. reinicia `salomao-prod.service`
8. testa `http://127.0.0.1:8100/api/v1/health`

## Auditoria de producao

No checkout `/srv/salomao/prod/app`:

```bash
./scripts/check-prod.sh
```

Esse script verifica:

- configuracao do `backend/.env`
- servico da aplicacao
- `nginx`
- `postgresql`
- `fail2ban`
- healthcheck local e publico
- portas de rede
- `UFW`
- configuracao efetiva do `sshd`
- certificado TLS

## Fonte de verdade do deploy

Os arquivos que devem orientar qualquer automacao ou processo futuro sao:

- `README.md`
- `docs/deploy-vps.md`
- `scripts/deploy-dev.sh`
- `scripts/deploy-prod.sh`
- `scripts/check-prod.sh`
