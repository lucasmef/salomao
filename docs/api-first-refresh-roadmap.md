# API-first refresh rollout

## Diretriz

Fontes principais do produto:

- API Linx
- API Inter

Fontes legadas apenas como backup:

- OFX
- importacao via tabela
- carga historica manual

## Objetivo desta fase

Criar uma base unica para refresh e invalidacao de cache, separando de forma explicita:

- fluxos principais (`primary_api`)
- fluxos de contingencia (`backup_manual`)

## Primeira entrega

- criar servico central `backend/app/services/data_refresh.py`
- consolidar matriz de impacto por familia de origem
- preparar o caminho para substituir invalidacoes espalhadas nas rotas e no auto sync

## Proximos passos

1. [x] Migrar `imports.py` para usar `build_data_refresh_request(...)` e `finalize_data_refresh(...)`
2. [x] Migrar `purchase_planning.py` para o mesmo fechamento central
3. [x] Migrar `linx_auto_sync.py` para usar o mesmo orquestrador no final de cada ciclo (Job `linx_auto_sync_refresh.py` acoplado em paralelo)
4. [ ] Revisar quais familias realmente precisam aquecer visoes live apos o sync
5. [x] Criar testes de coerencia pos-sync

## Workflow & Schedulers (CI/CD Sync)

> **ATENÇÃO:** A arquitetura legada (systemd timer) foi preterida em favor da rotina CI/CD via scripts no servidor, gerida pela branch `dev`. Para garantir a estratégia dual-job aprovada, o job antigo (`app.jobs.linx_auto_sync`) E o job novo (`app.jobs.linx_auto_sync_refresh`) devem ser configurados em ambiente de Produção como complementares no crontab ou scheduler interno da VPS.
