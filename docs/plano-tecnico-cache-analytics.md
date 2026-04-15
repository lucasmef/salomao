# Plano técnico - cache e materialização de analytics

## Objetivo

Corrigir dados antigos travados, reduzir latência da Visão Geral e do DRE, e transformar o cache atual em uma estratégia mais previsível de materialização live + snapshots históricos.

## Diagnóstico resumido

### Problemas encontrados

1. Há invalidação incompleta em fluxos de importação e sincronização que alteram dados usados por dashboard, cashflow e relatórios.
2. O DRE carrega lançamentos demais e filtra em Python, o que deixa a reconstrução cara.
3. O cashflow tem custo alto de recomputação e sinais de N+1 em transferências.
4. A materialização está forte apenas para histórico. O mês atual ainda depende demais de rebuild completo + Redis.
5. Existem trechos legados de cache em memória que geram ruído técnico.

## Ordem recomendada de implementação

---

## Etapa 1 - corrigir invalidação de cache

### Objetivo
Garantir que toda mutação que impacta analytics invalide cache live e requeue snapshots históricos quando necessário.

### Arquivo principal
- `backend/app/api/routes/imports.py`

### Ajustes

#### 1.1 Invalidar analytics após `upload_linx_receivables`
Adicionar chamada a `clear_finance_analytics_caches(...)` após a importação.

Requisitos:
- invalidar dashboard, reports e cashflow
- passar `db=db` e `company=company`
- incluir `affected_dates` quando possível com base nas datas importadas

#### 1.2 Invalidar analytics após `trigger_linx_receivables_sync`
Adicionar chamada a `clear_finance_analytics_caches(...)`.

Requisitos:
- usar `affected_dates=[payload.start_date, payload.end_date]` filtrando `None`
- manter comportamento consistente com os outros syncs já invalidados

#### 1.3 Invalidar analytics após `trigger_linx_open_receivables_sync`
Adicionar chamada a `clear_finance_analytics_caches(...)`.

Requisitos:
- invalidar cache mesmo em `full_refresh`
- avaliar se deve incluir `include_sales_history=False` ou `True` conforme impacto real

### Critério de aceite
- após importar ou sincronizar recebíveis, os endpoints de dashboard, cashflow e reports não podem continuar servindo payload antigo do Redis
- período atual deve refletir os novos dados sem depender de expiração por TTL

---

## Etapa 2 - reduzir o custo do DRE e DRO

### Objetivo
Parar de carregar o universo inteiro de `FinancialEntry` para depois filtrar em memória.

### Arquivo principal
- `backend/app/services/reports.py`

### Ajustes

#### 2.1 Restringir query por período já no SQL
Hoje `build_reports_overview()` traz todos os lançamentos válidos da empresa e filtra depois.

Implementar estratégia para separar por base temporal:
- DRE: filtrar por `competence_date`, fallback para `issue_date`, fallback para `due_date`
- DRO: filtrar por `due_date`, fallback para `competence_date`, fallback para `issue_date`

Observação:
Como há fallback entre campos, pode ser necessário:
- criar expressão SQL com `coalesce`, ou
- manter uma query com janela maior mas ainda limitada por datas relevantes, ou
- materializar uma `effective_date` por regime

#### 2.2 Evitar dupla leitura completa de `FinancialEntry`
Hoje DRE e DRO fazem leituras separadas e amplas.

Avaliar uma destas abordagens:
- uma única carga enxuta para o período e reuso em memória
- duas queries específicas, porém cada uma já filtrada por período e campos mínimos

#### 2.3 Agregar mais cedo
Empurrar o máximo possível de agregação por categoria/grupo para SQL, em vez de fazer breakdown todo em Python.

Priorizar:
- despesas operacionais
- despesas financeiras
- despesas não operacionais
- impostos sobre lucro
- compras pagas

### Critério de aceite
- redução perceptível no tempo de resposta de `/reports/overview`
- redução proporcional no tempo de resposta de `/dashboard/overview`
- menor uso de CPU e memória em refresh forçado

---

## Etapa 3 - otimizar cashflow

### Objetivo
Eliminar recomputações caras e N+1 na montagem do saldo atual e projeções.

### Arquivo principal
- `backend/app/services/cashflow.py`

### Ajustes

#### 3.1 Reescrever `_current_balance_for_account`
Evitar loop por conta com leitura completa dos lançamentos da conta.

Trocar por agregação SQL por conta:
- somar entradas realizadas
- somar saídas realizadas
- tratar transferências com join na tabela `Transfer`

#### 3.2 Eliminar `db.get(Transfer, entry.transfer_id)` dentro de loops
Substituir por:
- join direto na query, ou
- pré-carregamento/indexação por `transfer_id`

#### 3.3 Otimizar `_future_events`
Reduzir custo de leitura de eventos futuros:
- buscar apenas colunas necessárias
- agregar por dia quando viável
- evitar objetos completos quando apenas valor e data são usados

### Critério de aceite
- `/dashboard/overview` e `/cashflow/overview` mais rápidos
- menos queries por requisição
- sem N+1 de transferência

---

## Etapa 4 - materialização live real do mês corrente

### Objetivo
Parar de depender apenas de rebuild completo + Redis para o mês atual.

### Arquivos principais
- `backend/app/services/analytics_hybrid.py`
- novos serviços/tabelas de agregação live

### Proposta

Criar agregados live por mês atual, por exemplo:
- `analytics_live_dre_daily`
- `analytics_live_cashflow_daily`
- ou uma tabela única com `kind`, `reference_date`, `company_id`, `params_key`

### Estratégia

#### 4.1 Atualização incremental por evento
Sempre que houver:
- criação/edição/baixa/cancelamento/exclusão de `FinancialEntry`
- importação de vendas
- importação de recebíveis
- conciliação
- desconciliação

atualizar somente os buckets/dias afetados.

#### 4.2 Redis passa a ser camada de entrega, não origem do cálculo
Usar Redis para resposta rápida em cima de dados já agregados.

#### 4.3 Snapshots históricos permanecem
Manter o snapshot mensal para histórico fechado.

### Critério de aceite
- refresh do mês atual quase instantâneo na maior parte dos casos
- menos recalculo completo
- menor sensibilidade a TTL

---

## Etapa 5 - reduzir inconsistência operacional

### Objetivo
Facilitar suporte e evitar confusão entre fonte de dados e cálculo real.

### Ajustes

#### 5.1 Atualizar documentação técnica
Revisar:
- `docs/mapa-calculos-sistema.md`

Alinhar o documento ao comportamento real atual de:
- DRE
- DRO
- dashboard
- cashflow
- snapshots históricos
- live cache

#### 5.2 Remover estruturas legadas de cache em memória não utilizadas
Revisar em:
- `backend/app/services/reports.py`
- `backend/app/services/cashflow.py`

Se o fluxo oficial é Redis + snapshot, remover caches locais mortos ou deixar explícito seu uso real.

### Critério de aceite
- código mais simples de manter
- menor ruído na depuração

---

## Testes obrigatórios

### Testes funcionais

1. Importar recebíveis e verificar atualização imediata da Visão Geral.
2. Sincronizar recebíveis e verificar atualização imediata do Cashflow.
3. Reconciliar um lançamento e verificar atualização do dashboard.
4. Alterar categoria de um lançamento e verificar atualização do DRE.
5. Editar lançamento histórico e verificar requeue/rebuild do snapshot do mês afetado.

### Testes de performance

Medir antes e depois:
- `/dashboard/overview`
- `/reports/overview`
- `/cashflow/overview`

Cenários:
- mês atual
- mês histórico
- intervalo multi-mês
- refresh forçado

### Testes de consistência

Validar que:
- payload com `refresh=false` não retorna dados antigos após mutações relevantes
- payload com `refresh=true` reconstrói sem divergência
- snapshots históricos são refeitos quando datas antigas são afetadas

---

## Entrega mínima recomendada para primeira PR

### PR 1
- corrigir invalidação em imports/syncs de recebíveis
- adicionar testes cobrindo esses fluxos

### PR 2
- otimizar query do DRE/DRO por período
- reduzir dupla carga de `FinancialEntry`

### PR 3
- otimizar saldo atual e eventos do cashflow
- eliminar N+1 de transferências

### PR 4
- introduzir materialização live incremental

---

## Resumo executivo

### Causa raiz mais provável dos dados travados
- invalidação incompleta em alguns fluxos críticos

### Causa raiz mais provável da lentidão
- rebuild caro de reports e cashflow no período atual

### Melhor direção arquitetural
- histórico fechado em snapshot mensal
- mês corrente com agregados live incrementais
- Redis apenas como camada de entrega rápida
