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

1. Migrar `imports.py` para usar `build_data_refresh_request(...)` e `finalize_data_refresh(...)`
2. Migrar `purchase_planning.py` para o mesmo fechamento central
3. Migrar `linx_auto_sync.py` para usar o mesmo orquestrador no final de cada ciclo
4. Revisar quais familias realmente precisam aquecer visoes live apos o sync
5. Criar testes de coerencia pos-sync
