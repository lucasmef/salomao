# Deploy no VPS da KingHost

Este projeto publica somente no VPS da KingHost.

Nao existe mais deploy local, empacotamento desktop ou fluxo operacional via executavel ou atalhos.

## Ambientes oficiais

- `dev`: homologacao no VPS
- `prod`: producao no VPS

## Branches oficiais

- branch `dev`: publica no ambiente `dev` por `push` e serve de base para promocoes manuais
- branch `main`: representa a linha de producao e so pode ser promovida manualmente por operador humano

Checkouts esperados no servidor:

- `/srv/salomao/dev/app` segue `origin/dev`
- `/srv/salomao/prod/app` segue o SHA imutavel implantado em producao

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
| `Refresh Dev DB` | manual | copia banco prod para dev com modo seguro |
| `Sanitize Dev DB` | manual | anonimizacao de dados sensiveis no banco dev |
| `Set Dev Safety Mode` | manual (`safe` ou `validate`) | liga ou desliga modo seguro no dev |

### Fluxo tipico

1. Desenvolver na branch `dev` e fazer `push` para `origin/dev`.
2. Acompanhar o workflow `Deploy Dev` pelo `gh` ate a conclusao.
3. Se houver falha, abrir os logs do run, corrigir o problema e fazer novo `push` em `dev`.
4. Validar o ambiente `dev` via `Tailscale`.
5. Quando precisar validar com dados reais: rodar `Refresh Dev DB`.
6. Quando a validacao terminar: rodar `Sanitize Dev DB`.
7. Quando pronto para producao, um operador humano executa manualmente o `Deploy Prod` e a promocao para `main`.

### Modo seguro

O ambiente dev nasce em modo seguro apos cada refresh de banco:

- `inter_api_enabled = false` em todas as contas
- credenciais Inter zeradas
- sessoes e dispositivos MFA invalidados
- alertas de email desabilitados

Para abrir uma janela de validacao: rodar `Set Dev Safety Mode` com modo `validate`.
Para fechar a janela: rodar com modo `safe`.

O ambiente `dev` nao possui host publico. O acesso acontece diretamente pela rede `Tailscale`.

## Politica obrigatoria de deploy

- A IA nunca faz deploy direto no servidor por SSH.
- O deploy normal de homologacao sempre comeca com `git push origin dev`.
- Depois do `push`, a IA deve localizar o run mais recente de `Deploy Dev` no `gh cli` e aguardar o termino.
- Se o run falhar, a IA deve consultar os logs, corrigir o problema no repositorio e repetir o ciclo com novo `push`.
- O deploy de producao e a promocao para `main` sao sempre manuais e nunca devem ser executados pela IA.

## Protocolo com `gh`

Sequencia obrigatoria depois de cada `push` em `dev`:

1. Identificar o run mais recente do workflow `Deploy Dev`.
2. Aguardar a execucao ate o status final.
3. Se falhar, abrir os logs do run e localizar o job ou etapa quebrada.
4. Corrigir localmente, commitar e fazer novo `push` em `dev`.

Comandos de referencia:

```bash
gh run list --workflow "Deploy Dev" --branch dev --limit 1
gh run watch <run-id> --exit-status
gh run view <run-id> --log-failed
```

Nao considere um deploy concluido sem acompanhar o run pelo `gh`.

## Arquivos de ambiente

O arquivo real de runtime deve ficar fora do repositorio, por padrao em `../salomao-config/backend.env`.

Os scripts tambem aceitam override via `SALOMAO_ENV_FILE` ou `BACKEND_ENV_FILE` e mantem `backend/.env` apenas como fallback legado.

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

Deploy normal exclusivamente via `push` na branch `dev`.

O disparo manual do workflow existe apenas como contingencia operacional humana. A IA nao deve usar `workflow_dispatch` para deploy em `dev`.

O workflow executa:

1. `sync-checkout-to-ref.sh /srv/salomao/dev/app dev`
2. `deploy-dev.sh`
3. healthcheck em `http://127.0.0.1:8101/api/v1/health`

O script `deploy-dev.sh` delega para `deploy-vps.sh dev`, que:

1. valida o arquivo de ambiente resolvido
2. valida `APP_MODE=server`
3. valida `DATABASE_URL` PostgreSQL
4. roda `npm ci`
5. roda `npm run build`
6. roda `alembic upgrade head`
7. reinicia `salomao-dev.service`
8. testa `http://127.0.0.1:8101/api/v1/health`

Esses passos acontecem dentro do `self-hosted runner` no VPS. Eles nao devem ser executados manualmente pela IA no host.

## Deploy de producao

Deploy sempre manual via GitHub Actions (`Deploy Prod`) promovendo o estado atual da branch `dev`.

A IA nao executa esse workflow e nao promove `main`.

Diferente do ambiente dev, a producao nao segue uma branch mutavel. O workflow resolve um SHA unico e imutavel a partir do `HEAD` de `dev` e garante que apenas esse commit seja implantado.

O workflow executa:

1. Resolucao e validacao do SHA alvo no `HEAD` de `dev`
2. `sync-checkout-to-ref.sh /srv/salomao/prod/app <TARGET_SHA>`
3. `deploy-prod.sh`
4. `check-prod.sh`
5. healthcheck em `http://127.0.0.1:8100/api/v1/health`

## Auditoria de producao

No checkout `/srv/salomao/prod/app`:

```bash
./scripts/check-prod.sh
```

Esse script verifica:

- configuracao do arquivo de ambiente resolvido
- servico da aplicacao
- `nginx`
- `postgresql`
- `fail2ban`
- healthcheck local e, na producao, healthcheck publico
- portas de rede
- `UFW`
- configuracao efetiva do `sshd`
- certificado TLS

## Acesso ao VPS

O acesso SSH fica sempre restrito ao Tailscale.

- Nao existe workflow para abrir ou fechar SSH.
- O SSH publico esta removido do firewall.
- A porta 22 esta liberada somente na interface `tailscale0`.
- SSH no VPS serve para observabilidade, auditoria e manutencao controlada, nao para deploy normal da IA.

Para detalhes de acesso: `docs/ssh-acesso-vps.md`.

## Scripts operacionais

| Script | Funcao |
| --- | --- |
| `scripts/deploy-dev.sh` | deploy do ambiente dev dentro do runner |
| `scripts/deploy-prod.sh` | deploy do ambiente prod dentro do runner |
| `scripts/deploy-vps.sh` | script centralizado de deploy usado pelos workflows |
| `scripts/check-prod.sh` | auditoria rapida de producao |
| `scripts/sync-checkout-to-ref.sh` | sincroniza checkout com ref remota |
| `scripts/refresh-dev-db-from-prod.sh` | copia banco prod para dev com pos-refresh |
| `scripts/post-refresh-dev.sh` | modo seguro apos refresh |
| `scripts/sanitize-dev-db.sh` | anonimizacao do banco dev |
| `scripts/set-dev-safety-mode.sh` | toggle de modo seguro |

## Fonte de verdade do deploy

Os arquivos que devem orientar qualquer automacao ou processo futuro sao:

- `README.md`
- `docs/deploy-vps.md`
- `.github/workflows/*.yml`
- `scripts/*.sh`
