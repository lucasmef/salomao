# Plano multi-servicos: Salomao e Doit

Status geral: `planejamento`
Ultima atualizacao: 2026-05-06

## Objetivo

Preparar o VPS para rodar quatro instancias independentes:

- `salomao` producao
- `salomao-dev` homologacao
- `doit` producao
- `doit-dev` homologacao

O Salomao em producao nao pode cair por muito tempo. A implantacao deve criar e validar a nova estrutura em paralelo, mantendo o servico atual ativo ate a troca final de Nginx.

Ambientes `dev` nao devem existir publicamente. O acesso de `salomao-dev` e `doit-dev` deve ser feito somente via Tailscale.

## Estado atual observado

Levantamento feito por SSH via Tailscale, sem alterar o servidor.

| Item | Estado |
| --- | --- |
| VPS | Ubuntu 24.04, host `raquel-talita.vps-kinghost.net` |
| SSH operacional | Funcionou via IP Tailscale `100.81.12.64`; alias DNS `salomao-vps` ficou lento/travando |
| `salomao-prod.service` | Ativo em `127.0.0.1:8100`, healthcheck `200` |
| `salomao-dev.service` | Ativo em `127.0.0.1:8101`, healthcheck `200` |
| `salomao-inter-dev.service` | Ativo em `127.0.0.1:8102`, mas healthcheck nao respondeu |
| Nginx publico atual | `raquel-talita.vps-kinghost.net` -> `127.0.0.1:8100` |
| Nginx dev atual | `salomao-vps.tail2033b8.ts.net` -> `127.0.0.1:8101` na configuracao atual; plano novo usa portas Tailscale dedicadas |
| Diretorio Doit | `/srv/doit` ainda nao existe |
| Servicos Doit | `doit.service` e `doit-dev.service` ainda nao existem |
| Instalacao Doit no VPS | Ainda nao configurada; sera uma instalacao nova |

## Estado local observado do Doit

Levantamento feito na pasta local `C:\Users\lucas\OneDrive\Documentos\doit.md`, sem editar o projeto.

| Item | Estado |
| --- | --- |
| Estrutura | Monorepo `pnpm` |
| App web | `apps/web`, Next.js 15 App Router, React 19, Tailwind, SWR |
| Banco | MongoDB via Mongoose em `packages/db` |
| Auth | Clerk |
| Integracoes | Google Calendar OAuth |
| Build | `apps/web/next.config.ts` usa `output: 'standalone'` |
| Healthcheck | `GET /api/health` retorna `{ ok: true }` |
| Deploy atual planejado | `scripts/deploy.sh <dev|prod> <porta>` |
| Units atuais | `infra/systemd/doit-web.service` e `doit-web-dev.service` |
| Portas atuais no Doit | prod `3000`, dev `3001` |
| Caminhos atuais no Doit | `/var/www/doit` e `/var/www/doit-dev` |
| Docker Compose | Sobe MongoDB, app e Nginx proprio nas portas `80/443` |
| Worktree Doit | Implementacao de deploy iniciada em arquivos de infra/workflow |

Conclusao inicial: o Doit precisa de ajustes de deploy para conviver com o Salomao no mesmo VPS. O `docker-compose.yml` atual nao deve ser usado como esta, porque tenta ocupar `80/443` com outro Nginx. A opcao de menor conflito e rodar o Next.js por systemd em portas locais e usar o Nginx host ja existente como proxy compartilhado.

## Decisoes pendentes

| Decisao | Status | Observacao |
| --- | --- | --- |
| Dominio publico exato do Salomao | `pendente` | Precisa ser FQDN sem acento, exemplo `salomao.raqueltalita-vps.com.br` |
| Dominio publico exato do Doit | `pendente` | Precisa ser FQDN, exemplo `doit.raqueltalita-vps.com.br` |
| Manter ou renomear `salomao-prod.service` | `recomendado manter` | Manter reduz risco e evita troca desnecessaria no Salomao |
| Destino de `salomao-inter-dev.service` | `pendente` | Decidir se sera removido, reaproveitado ou mantido fora do plano |
| Banco de dados do Doit | `pendente` | Confirmar MongoDB Atlas vs local; usar databases separados |
| Branch/repositorio do Doit | `parcial` | Repositorio local inspecionado em `C:\Users\lucas\OneDrive\Documentos\doit.md` |

## Topologia alvo proposta

| Aplicacao | Ambiente | Service | Porta local | Checkout | Exposicao |
| --- | --- | --- | --- | --- | --- |
| Salomao | prod | `salomao-prod.service` | `8100` | `/srv/salomao/prod/app` | publico via dominio novo |
| Salomao | dev | `salomao-dev.service` | `8101` | `/srv/salomao/dev/app` | Tailscale `:8443` |
| Doit | prod | `doit.service` | `8110` | `/srv/doit/prod/app` | publico via dominio novo |
| Doit | dev | `doit-dev.service` | `8111` | `/srv/doit/dev/app` | Tailscale `:8444` |

Portas internas `8100` e `8101` permanecem intactas. A porta `8102` fica reservada ate decidir o destino do `salomao-inter-dev.service`. O acesso externo aos ambientes dev deve ser feito por portas HTTPS privadas no Tailscale, nao por dominio publico.

## Principios de downtime minimo

- Nao parar `salomao-prod.service` durante a preparacao.
- Nao editar o site Nginx publico atual antes de o novo dominio do Salomao estar validado.
- Nao criar DNS, server block ou certificado publico para ambientes `dev`.
- Liberar portas `8443` e `8444` somente na interface `tailscale0`, se UFW estiver ativo.
- Criar novos arquivos Nginx em `sites-available` e testar com `nginx -t` antes de habilitar.
- Preferir `nginx reload` em vez de restart quando a configuracao estiver valida.
- Fazer a troca publica do Salomao em uma unica janela curta: DNS ja apontado, certificado emitido, upstream local validado, reload do Nginx.
- Manter rollback pronto para voltar o host publico atual para `127.0.0.1:8100`.

## Etapas de implementacao

### Fase 0: Confirmacoes

Status: `pendente`

- Confirmar FQDN publico exato do Salomao.
- Confirmar FQDN publico exato do Doit.
- Confirmar se Doit deve usar o repositorio local `C:\Users\lucas\OneDrive\Documentos\doit.md` como fonte.
- Confirmar se MongoDB sera Atlas ou MongoDB local no VPS.
- Confirmar nomes dos bancos MongoDB de prod/dev.
- Confirmar se `salomao-inter-dev.service` pode ser parado/removido em etapa futura.

### Fase 1: Preparar codigo e automacao local

Status: `pendente`

- Generalizar scripts de deploy para aceitar aplicacao e ambiente sem duplicacao excessiva.
- Parametrizar service name, porta, app dir e healthcheck.
- Atualizar workflows GitHub Actions para suportar deploys separados.
- Atualizar scripts de auditoria para checar portas `8100`, `8101`, `8110` e `8111`.
- Atualizar docs de arquitetura e deploy.
- No Doit, substituir paths `/var/www/doit*` por `/srv/doit/*/app`.
- No Doit, substituir services `doit-web*` por `doit*` ou decidir manter nomes atuais.
- No Doit, evitar Docker Compose com Nginx proprio em `80/443` no VPS compartilhado.
- No Doit, garantir que `next start` receba a porta correta ou que `PORT` esteja definido no unit systemd.

Validacao local:

```powershell
python scripts/security_scan.py
cd backend; $env:PYTHONPATH='.'; uv run pytest
cd frontend; npm run typecheck
cd frontend; npm run build
cd ..\doit.md; pnpm --filter @doit/web exec tsc --noEmit
cd ..\doit.md; pnpm --filter @doit/web build
```

### Fase 2: Preparar Doit no VPS sem tocar no Salomao

Status: `pendente`

- Criar `/srv/doit/prod/app` e `/srv/doit/dev/app`.
- Criar arquivos de ambiente fora do repo:
  - `/srv/doit/prod/doit-config/web.env`
  - `/srv/doit/dev/doit-config/web.env`
- Criar bancos MongoDB separados para Doit ou databases separados no Atlas.
- Criar `doit.service` na porta `8110`.
- Criar `doit-dev.service` na porta `8111`.
- Preparar Nginx dev privado em `8444` e UFW somente em `tailscale0`.
- Validar healthchecks locais:

```bash
curl --fail http://127.0.0.1:8110/api/health
curl --fail http://127.0.0.1:8111/api/health
```

Rollback da fase:

- Parar e desabilitar `doit.service` e `doit-dev.service`.
- Remover somente configs Nginx/units criadas para Doit, se existirem.
- Nao alterar `salomao-prod.service` nem `salomao-dev.service`.

### Fase 2b: Corrigir acesso Tailscale do Salomao dev

Status: `em andamento`

- Atualizar `setup-tailscale-nginx.sh` para expor Salomao dev em `https://salomao-vps.tail2033b8.ts.net:8443`.
- Manter backend interno do Salomao dev em `127.0.0.1:8101`.
- Nao criar host publico de dev.
- Liberar `8443/tcp` somente em `tailscale0`, se UFW estiver ativo.
- Rodar `nginx -t`.
- Aplicar `systemctl reload nginx`.

Rollback:

- Restaurar configuracao anterior de `salomao-dev-tailscale`.
- Rodar `nginx -t`.
- Aplicar `systemctl reload nginx`.

### Fase 3: Configurar Nginx para Doit

Status: `pendente`

- Validar DNS do dominio publico Doit apontando para o VPS.
- Emitir certificado TLS do Doit.
- Criar site Nginx do Doit apontando para `127.0.0.1:8110`.
- Criar acesso dev do Doit somente via Tailscale em `https://salomao-vps.tail2033b8.ts.net:8444`, apontando para `127.0.0.1:8111`.
- Nao criar `dev.dominio-publico` para Doit.
- Rodar `nginx -t`.
- Aplicar `systemctl reload nginx`.
- Validar:

```bash
curl --fail https://<dominio-doit>/api/health
curl --fail https://salomao-vps.tail2033b8.ts.net:8444/api/health
```

Rollback da fase:

- Desabilitar links Nginx do Doit.
- Rodar `nginx -t`.
- Aplicar `systemctl reload nginx`.

### Fase 4: Preparar novo dominio publico do Salomao

Status: `pendente`

- Validar DNS do dominio publico Salomao apontando para o VPS.
- Emitir certificado TLS do novo dominio Salomao.
- Criar novo site Nginx do Salomao apontando para `127.0.0.1:8100`, sem remover o host antigo ainda.
- Rodar `nginx -t`.
- Aplicar `systemctl reload nginx`.
- Validar novo dominio:

```bash
curl --fail https://<dominio-salomao>/api/v1/health
```

Rollback da fase:

- Desabilitar somente o novo site Nginx do Salomao.
- Manter host publico antigo funcionando.

### Fase 5: Troca final do Salomao

Status: `pendente`

Pre-condicoes:

- `salomao-prod.service` ativo e healthcheck local `200`.
- Host publico antigo ainda funcionando.
- Novo dominio Salomao com TLS e healthcheck publico `200`.
- Rollback testado por `nginx -t`.

Execucao:

- Reduzir TTL de DNS antes da janela, se o provedor permitir.
- Apontar usuarios para o novo dominio.
- Manter host antigo temporariamente como redirecionamento ou compatibilidade, conforme decisao operacional.
- Monitorar logs do Nginx e `salomao-prod.service`.

Rollback:

- Voltar DNS/roteamento para o host antigo.
- Restaurar link Nginx anterior, se necessario.
- `systemctl reload nginx`.
- Confirmar `curl --fail http://127.0.0.1:8100/api/v1/health`.

## Quadro de evolucao

| Data | Responsavel | Item | Status | Evidencia/observacao |
| --- | --- | --- | --- | --- |
| 2026-05-06 | Codex | Levantamento SSH read-only | `feito` | Salomao prod/dev saudaveis; Doit inexistente |
| 2026-05-06 | Codex | Plano inicial criado | `feito` | Este documento |
| 2026-05-06 | Codex | Levantamento local Doit | `feito` | Next.js 15, MongoDB/Mongoose, Clerk, Google OAuth, pnpm |
| 2026-05-06 | Lucas | Regra dev somente Tailscale | `feito` | Nenhum ambiente dev deve existir publicamente |
| 2026-05-06 | Lucas | Doit no VPS | `feito` | Confirmado que ainda nao foi configurado no VPS |
| 2026-05-06 | Lucas | Salomao dev pode cair | `feito` | Permite corrigir a topologia dev sem restricao de downtime no dev |
| 2026-05-06 | Codex | Implementar deploy local Doit | `em andamento` | Scripts, workflows, systemd e Nginx templates em edicao |
| 2026-05-06 | Codex | Separar dev Tailscale por porta | `em andamento` | Salomao dev `:8443`; Doit dev `:8444` |
| 2026-05-06 | Codex | Staging no VPS | `feito` | Arquivos preparados em `/srv/salomao/shared/doit-vps-staging` |
| 2026-05-06 | Lucas | Aplicacao root no VPS | `feito` | `/srv/doit`, Nginx dev Tailscale, UFW e units criados |
| 2026-05-06 | Codex | Validar Salomao dev Tailscale | `feito` | `https://salomao-vps.tail2033b8.ts.net:8443/api/v1/health` retornou `200` |
| 2026-05-06 | Codex | Preparar Doit dev app | `parcial` | Codigo copiado para `/srv/doit/dev/app`; install passou; build bloqueado por env placeholder Clerk |
| 2026-05-06 | Lucas | Corrigir pnpm no systemd Doit | `feito` | Units instaladas usam `/usr/bin/corepack pnpm` |
| 2026-05-06 | Codex | Validar env Doit dev | `bloqueado` | `web.env` ainda tem placeholders em Clerk e Google; Doit dev fica `502` ate o app subir |
| 2026-05-06 | Codex | Configurar env Doit dev | `feito` | `web.env` preenchido no VPS sem placeholders; values nao registrados no repo |
| 2026-05-06 | Codex | MongoDB local Doit dev | `pendente root` | `localhost:27017` fechado; script root preparado em `/srv/salomao/shared/doit-vps-staging/install-mongodb-root.sh` |
| 2026-05-06 | Codex | Deploy Doit dev root helper | `pendente root` | Script preparado em `/srv/salomao/shared/doit-vps-staging/deploy-doit-dev-root.sh` |
| 2026-05-06 | Lucas | Novo dominio Salomao prod | `feito` | `https://salomao.raquel-talita.vps-kinghost.net/api/v1/health` retornou `200` |
| 2026-05-06 | Codex | Auditoria prod apos dominio | `feito` | `/srv/salomao/prod/app/scripts/check-prod.sh` passou com `FAIL=0` |
|  |  | Confirmar dominios finais | `pendente` |  |
|  |  | Confirmar origem do codigo Doit | `pendente` |  |
|  |  | Confirmar MongoDB Atlas vs local | `pendente` |  |
|  |  | Implementar scripts parametrizados | `pendente` |  |
|  |  | Validar deploy dev Salomao sem regressao | `pendente` |  |
|  |  | Criar servicos Doit no VPS | `pendente` |  |
|  |  | Validar Doit local no VPS | `pendente` |  |
|  |  | Publicar Doit no Nginx | `pendente` |  |
|  |  | Publicar novo dominio Salomao | `pendente` |  |

## Riscos principais

- DNS incompleto ou apontando para IP incorreto impede TLS publico.
- Trocar Nginx do Salomao antes de validar o novo dominio pode causar indisponibilidade publica.
- Reaproveitar `8102` conflita com `salomao-inter-dev.service`.
- Usar o `docker-compose.yml` atual do Doit no VPS compartilhado conflita com o Nginx existente em `80/443`.
- Criar Doit dev com host publico viola a regra operacional; dev deve ficar somente via Tailscale.
- Misturar databases MongoDB de prod/dev pode misturar dados; manter databases separados.
- Alterar workflows de producao sem validar em dev pode travar deploy manual.

## Fora do escopo ate nova aprovacao

- Deploy direto de producao por SSH.
- Promocao para `main`.
- Parar ou remover `salomao-inter-dev.service`.
- Renomear `salomao-prod.service`.
- Migrar dados entre Salomao e Doit.
