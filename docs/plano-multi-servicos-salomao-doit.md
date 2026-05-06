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
| Nginx dev atual | `salomao-vps.tail2033b8.ts.net` -> `127.0.0.1:8101` |
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
| Worktree Doit | Possui alteracoes locais nao commitadas |

Conclusao inicial: o Doit precisa de ajustes de deploy para conviver com o Salomao no mesmo VPS. O `docker-compose.yml` atual nao deve ser usado como esta, porque tenta ocupar `80/443` com outro Nginx. A opcao de menor conflito e rodar o Next.js por systemd em portas locais e usar o Nginx host ja existente como proxy compartilhado.

## Decisoes pendentes

| Decisao | Status | Observacao |
| --- | --- | --- |
| Dominio publico exato do Salomao | `pendente` | Precisa ser FQDN sem acento, exemplo `salomao.raqueltalita-vps.com.br` |
| Dominio publico exato do Doit | `pendente` | Precisa ser FQDN, exemplo `doit.raqueltalita-vps.com.br` |
| Manter ou renomear `salomao-prod.service` | `recomendado manter` | Manter reduz risco e evita troca desnecessaria no Salomao |
| Destino de `salomao-inter-dev.service` | `pendente` | Decidir se sera removido, reaproveitado ou mantido fora do plano |
| Banco de dados do Doit | `pendente` | Sugerido: `doit_prod` e `doit_dev` |
| Branch/repositorio do Doit | `pendente` | Confirmar se e o mesmo repositorio com configuracao distinta ou outro repo |

## Topologia alvo proposta

| Aplicacao | Ambiente | Service | Porta local | Checkout | Exposicao |
| --- | --- | --- | --- | --- | --- |
| Salomao | prod | `salomao-prod.service` | `8100` | `/srv/salomao/prod/app` | publico via dominio novo |
| Salomao | dev | `salomao-dev.service` | `8101` | `/srv/salomao/dev/app` | privado via Tailscale |
| Doit | prod | `doit.service` | `8110` | `/srv/doit/prod/app` | publico via dominio novo |
| Doit | dev | `doit-dev.service` | `8111` | `/srv/doit/dev/app` | somente Tailscale |

Portas `8100` e `8101` permanecem intactas para minimizar risco no Salomao. A porta `8102` fica reservada ate decidir o destino do `salomao-inter-dev.service`.

## Principios de downtime minimo

- Nao parar `salomao-prod.service` durante a preparacao.
- Nao editar o site Nginx publico atual antes de o novo dominio do Salomao estar validado.
- Nao criar DNS, server block ou certificado publico para ambientes `dev`.
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
  - `/srv/doit/prod/doit-config/backend.env`
  - `/srv/doit/dev/doit-config/backend.env`
- Criar bancos MongoDB separados para Doit ou databases separados no Atlas.
- Criar `doit.service` na porta `8110`.
- Criar `doit-dev.service` na porta `8111`.
- Validar healthchecks locais:

```bash
curl --fail http://127.0.0.1:8110/api/v1/health
curl --fail http://127.0.0.1:8111/api/v1/health
```

Rollback da fase:

- Parar e desabilitar `doit.service` e `doit-dev.service`.
- Remover somente configs Nginx/units criadas para Doit, se existirem.
- Nao alterar `salomao-prod.service` nem `salomao-dev.service`.

### Fase 3: Configurar Nginx para Doit

Status: `pendente`

- Validar DNS do dominio publico Doit apontando para o VPS.
- Emitir certificado TLS do Doit.
- Criar site Nginx do Doit apontando para `127.0.0.1:8110`.
- Criar acesso dev do Doit somente via Tailscale apontando para `127.0.0.1:8111`.
- Nao criar `dev.dominio-publico` para Doit.
- Rodar `nginx -t`.
- Aplicar `systemctl reload nginx`.
- Validar:

```bash
curl --fail https://<dominio-doit>/api/health
curl --fail https://<host-tailscale-doit-dev>/api/health
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
