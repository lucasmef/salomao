# Deploy no VPS da KingHost

Este projeto publica somente no VPS da KingHost.

Nao existe mais deploy local, empacotamento desktop ou fluxo operacional via executavel/atalhos.

## Ambientes oficiais

- `dev`: homologacao no VPS
- `prod`: producao no VPS

## Branches oficiais

- branch `dev` publica no ambiente `dev` (homologacao)
- branch `main` publica no ambiente `prod` (producao)

Checkouts esperados no servidor:

- `/srv/salomao/dev/app` → segue `origin/dev`
- `/srv/salomao/prod/app` → segue `origin/main`

Servicos esperados:

- `salomao-dev.service`
- `salomao-prod.service`

## CI/CD com GitHub Actions

O deploy e feito via `self-hosted runner` rodando no proprio VPS.
Os workflows nao dependem de chave SSH local nem de acesso externo.
O SSH fica sempre restrito ao Tailscale.

### Workflows disponiveis

| Workflow | Trigger | Funcao |
| --- | --- | --- |
| `Deploy Dev` | push em `dev` + manual | deploy automatico do ambiente dev |
| `Deploy Prod` | manual | deploy manual da producao |
| `Refresh Dev DB` | manual | copia banco prod → dev com modo seguro |
| `Sanitize Dev DB` | manual | anonimizacao de dados sensiveis no banco dev |
| `Set Dev Safety Mode` | manual (safe/validate) | liga ou desliga modo seguro no dev |

### Fluxo tipico

1. Desenvolver na branch `dev` e fazer push → deploy automatico no ambiente dev
2. Quando precisar validar com dados reais: rodar `Refresh Dev DB`
3. Testar no ambiente dev com dados reais (janela de validacao)
4. Quando a validacao terminar: rodar `Sanitize Dev DB`
5. Quando pronto para producao: merge `dev → main` e rodar `Deploy Prod`

### Modo seguro

O ambiente dev nasce em modo seguro apos cada refresh de banco:

- `inter_api_enabled = false` em todas as contas
- credenciais Inter zeradas
- sessoes e dispositivos MFA invalidados
- alertas de email desabilitados

Para abrir uma janela de validacao: rodar `Set Dev Safety Mode` com modo `validate`.
Para fechar a janela: rodar com modo `safe`.

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

Deploy automatico via push na branch `dev`, ou manual via GitHub Actions.

O workflow executa:

1. `sync-checkout-to-ref.sh /srv/salomao/dev/app dev`
2. `deploy-dev.sh`
3. healthcheck em `http://127.0.0.1:8101/api/v1/health`

O script `deploy-dev.sh` delega para `deploy-vps.sh dev`, que:

1. valida `backend/.env`
2. valida `APP_MODE=server`
3. valida `DATABASE_URL` PostgreSQL
4. roda `npm ci`
5. roda `npm run build`
6. roda `alembic upgrade head`
7. reinicia `salomao-dev.service`
8. testa `http://127.0.0.1:8101/api/v1/health`

## Deploy de producao

Deploy sempre manual via GitHub Actions (`Deploy Prod`).

O workflow executa:

1. `sync-checkout-to-ref.sh /srv/salomao/prod/app main`
2. `deploy-prod.sh`
3. `check-prod.sh`
4. healthcheck em `http://127.0.0.1:8100/api/v1/health`

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

## Acesso ao VPS

O acesso SSH fica sempre restrito ao Tailscale.

- Nao existe workflow para abrir ou fechar SSH.
- O SSH publico esta removido do firewall.
- A porta 22 esta liberada somente na interface `tailscale0`.

Para detalhes de acesso: `docs/ssh-acesso-vps.md`.

## Scripts operacionais

| Script | Funcao |
| --- | --- |
| `scripts/deploy-dev.sh` | deploy do ambiente dev |
| `scripts/deploy-prod.sh` | deploy do ambiente prod |
| `scripts/deploy-vps.sh` | script centralizado de deploy |
| `scripts/check-prod.sh` | auditoria rapida de producao |
| `scripts/sync-checkout-to-ref.sh` | sincroniza checkout com ref remota |
| `scripts/refresh-dev-db-from-prod.sh` | copia banco prod → dev com pos-refresh |
| `scripts/post-refresh-dev.sh` | modo seguro apos refresh |
| `scripts/sanitize-dev-db.sh` | anonimizacao do banco dev |
| `scripts/set-dev-safety-mode.sh` | toggle de modo seguro |

## Fonte de verdade do deploy

Os arquivos que devem orientar qualquer automacao ou processo futuro sao:

- `README.md`
- `docs/deploy-vps.md`
- `.github/workflows/*.yml`
- `scripts/*.sh`
