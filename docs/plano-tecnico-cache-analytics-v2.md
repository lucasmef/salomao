# Plano técnico - cache e materialização de analytics v2

## Objetivo

Fazer com que dashboard, DRE, DRO e cashflow:

- carreguem o mais rápido possível
- atualizem imediatamente quando necessário
- permitam filtro por data sem custo alto de rebuild completo
- tratem histórico e período atual com estratégias diferentes

## Regra operacional desejada

### Faixa histórica
Tudo exceto:
- futuro
- mês atual
- mês anterior

Características desejadas:
- não muda com frequência
- deve responder muito rápido
- se houver alteração retroativa, não pode demorar para refletir

### Faixa live
Inclui:
- mês atual
- mês anterior
- futuro

Características desejadas:
- deve carregar imediatamente
- deve atualizar imediatamente
- não pode depender de expiração lenta de TTL para refletir mudanças

## Direção arquitetural recomendada

A melhor estratégia para esse cenário é:

- materialização por data para analytics
- histórico persistido por dia
- camada live em Redis para janelas quentes
- rebuild granular por dia afetado, não por mês inteiro, quando houver alteração retroativa

Isso atende melhor o filtro por data do que snapshots mensais puros.

---

## Arquitetura alvo

## 1. Unidade principal de materialização: dia

Em vez de depender de materialização mensal como principal unidade, a base deve ser diária.

### Motivo
O usuário pode filtrar qualquer intervalo de datas. Se os agregados forem diários:
- períodos curtos ficam rápidos
- períodos longos continuam rápidos via soma de dias já agregados
- alterações retroativas afetam apenas os dias tocados
- evita rebuild desnecessário de mês inteiro

### Modelo sugerido
Criar uma tabela de agregados diários, ou mais de uma, por exemplo:

- `analytics_daily_fact`
- ou tabelas especializadas:
  - `analytics_daily_reports`
  - `analytics_daily_cashflow`
  - `analytics_daily_dashboard_inputs`

### Campos mínimos sugeridos
- `company_id`
- `reference_date`
- `kind`
- `params_key` quando necessário
- `gross_revenue`
- `deductions`
- `net_revenue`
- `cmv`
- `operating_expenses`
- `financial_expenses`
- `non_operating_income`
- `non_operating_expenses`
- `taxes_on_profit`
- `profit_distribution`
- `cash_inflows`
- `cash_outflows`
- `projected_inflows`
- `projected_outflows`
- `current_balance_delta` ou colunas equivalentes por domínio
- `updated_at`

Observação:
Não precisa ser uma tabela monolítica se isso atrapalhar o domínio. O ponto principal é que a granularidade base seja data.

---

## 2. Estratégia por faixa temporal

## 2.1 Histórico

### Escopo
Tudo antes do primeiro dia do mês anterior.

Exemplo prático considerando abril de 2026:
- histórico: até 31/01/2026
- live: 01/02/2026 em diante

### Estratégia
- usar materialização persistida por dia no banco
- leitura preferencial a partir dessa tabela materializada
- se houver alteração em dado histórico, recalcular apenas os dias afetados
- se necessário, recalcular também dias derivados impactados por saldo acumulado

### Comportamento esperado
- leitura extremamente rápida
- atualização retroativa também rápida, porque o rebuild é localizado

## 2.2 Live

### Escopo
- mês anterior
- mês atual
- futuro

### Estratégia
- manter agregados live por dia em Redis
- invalidar e recomputar imediatamente ao alterar eventos relevantes
- quando necessário, também persistir o agregado diário no banco como apoio de recuperação

### Comportamento esperado
- tela abre rápida
- alteração aparece imediatamente
- não depende de TTL alto para destravar dado antigo

---

## 3. Papel do Redis

Redis deve ser a camada de entrega rápida das janelas quentes, não a única fonte de verdade.

### Redis deve guardar
- payloads agregados da faixa live
- agregados diários quentes para compor visões rápidas
- índices auxiliares por empresa/faixa/kind

### Redis não deve ser responsável sozinho por coerência
Toda alteração relevante deve:
- invalidar a chave live afetada
- recomputar o agregado diário afetado
- regravar a resposta live imediatamente

### Regra sugerida
- sem confiar em TTL como mecanismo principal de atualização
- TTL pode existir só como proteção operacional
- a coerência deve vir por invalidação + recompute imediato

---

## 4. Como responder filtros por data

### Estratégia recomendada
Ao consultar um intervalo qualquer:

1. dividir o intervalo em dias
2. para dias históricos, ler da materialização persistida
3. para dias live, ler do Redis ou reconstruir imediatamente se estiver ausente
4. consolidar os dias consultados no payload final

### Vantagem
Um filtro como:
- 10 dias
- 45 dias
- 6 meses
- 2 anos

usa a mesma base: agregados diários.

Isso elimina a rigidez de snapshot mensal como unidade principal de leitura.

---

## Rebuild e invalidação

## 5. Regra de rebuild

### 5.1 Alterações em histórico
Quando uma alteração atingir data histórica:

- identificar os dias afetados
- rebuildar apenas esses dias
- se o dado impactar saldo acumulado ou projeção dependente de carry-forward, rebuildar também a janela derivada necessária

Exemplo:
- mudança em 2025-11-17
- recalcular agregado de 2025-11-17
- se isso altera saldo acumulado diário, recalcular forward a partir dali até a fronteira necessária

### 5.2 Alterações em live
Quando a alteração atingir:
- mês anterior
- mês atual
- futuro

Deve ocorrer:
- invalidação imediata do Redis afetado
- recomputação imediata do dia afetado
- atualização imediata dos payloads de overview, reports e cashflow afetados

---

## Regras específicas por domínio

## 6. DRE e DRO

### Problema atual
Hoje o rebuild é caro porque `FinancialEntry` é carregado demais e filtrado em Python.

### Estratégia alvo
- gerar fatos diários por regime de competência e por regime de caixa
- guardar por data efetiva relevante
- montar DRE e DRO por soma de dias, não por releitura completa dos lançamentos

### Resultado esperado
- filtros por data ficam rápidos
- DRE não precisa reconstruir tudo toda vez
- Visão Geral melhora junto, porque depende desses números

---

## 7. Cashflow

### Estratégia alvo
Separar claramente:
- fatos realizados por dia
- eventos futuros projetados por dia
- saldo acumulado derivado

### Materialização sugerida
- entradas realizadas por dia
- saídas realizadas por dia
- entradas projetadas por dia
- saídas projetadas por dia
- saldo de abertura e fechamento por dia, quando fizer sentido persistir

### Observação importante
Se o saldo diário for derivado de carry-forward, alteração em um dia pode exigir recomputar dias seguintes.

Solução recomendada:
- persistir fatos do dia
- calcular saldo acumulado em uma rotina incremental eficiente
- rebuildar forward somente da data alterada até o fim da janela live ou até a fronteira histórica relevante

---

## 8. Dashboard / Visão Geral

A Visão Geral não deve recalcular fundamentos pesados em tempo real.

Ela deve consumir:
- fatos diários já agregados de DRE e DRO
- fatos diários já agregados de cashflow
- contadores auxiliares atualizados por invalidação dirigida

### Resultado esperado
- abertura imediata
- atualização imediata após mutação relevante
- menor acoplamento a queries pesadas

---

## Implementação recomendada por etapas

## Etapa 1 - corrigir invalidação imediata do live atual

### Objetivo
Eliminar o sintoma de dados travados agora, antes da nova arquitetura completa.

### Ajustes
Corrigir todos os fluxos que alteram dados e hoje não invalidam analytics corretamente, principalmente em:
- `backend/app/api/routes/imports.py`

Prioridade:
- `upload_linx_receivables`
- `trigger_linx_receivables_sync`
- `trigger_linx_open_receivables_sync`

### Critério de aceite
- alteração relevante em recebíveis deve refletir imediatamente em dashboard, reports e cashflow

---

## Etapa 2 - introduzir materialização diária persistida

### Objetivo
Trocar o eixo principal de materialização de mês para dia.

### Ajustes
Criar estrutura de agregados diários e rotina de rebuild por dia.

### Regras
- histórico persistido por dia
- dias podem ser recalculados individualmente
- consultas por intervalo somam dias já materializados

### Critério de aceite
- consultas históricas por data muito rápidas
- alteração retroativa não exige rebuild global do mês inteiro

---

## Etapa 3 - criar camada live diária em Redis

### Objetivo
Garantir resposta imediata para mês anterior, mês atual e futuro.

### Ajustes
Manter no Redis:
- agregados diários live
- payloads prontos das visões mais acessadas

### Regra
Toda mutação relevante deve disparar:
- invalidação dirigida
- recompute do dia
- refresh das respostas dependentes

### Critério de aceite
- faixa live responde imediatamente
- sem esperar TTL expirar

---

## Etapa 4 - refatorar DRE e DRO para consumir fatos diários

### Objetivo
Parar de recalcular DRE e DRO lendo universo amplo de lançamentos.

### Ajustes
`backend/app/services/reports.py`

Migrar de:
- leitura ampla de `FinancialEntry` + filtro em Python

Para:
- leitura de agregados diários já preparados
- fallback pontual só em rebuild

### Critério de aceite
- DRE muito mais rápido
- filtros de data eficientes

---

## Etapa 5 - refatorar cashflow para consumo incremental

### Objetivo
Eliminar custo alto e N+1, e suportar carry-forward eficiente.

### Ajustes
`backend/app/services/cashflow.py`

Migrar para:
- fatos diários materializados
- recomputação forward apenas quando necessário
- menos query por conta e menos laço em memória

### Critério de aceite
- cashflow rápido
- atualização imediata após mutação

---

## Regras de fronteira

## 9. Política temporal recomendada

Em produção, usar uma fronteira explícita baseada na data corrente:

- live window = do primeiro dia do mês anterior em diante
- historical window = tudo antes disso

### Por que incluir o mês anterior no live
Porque ainda pode haver:
- baixas retroativas
- conciliações tardias
- ajustes de categoria
- correções operacionais

Isso reduz risco de inconsistência em uma faixa ainda sujeita a alteração.

---

## Testes obrigatórios

## 10. Testes funcionais

1. Alterar dado histórico e verificar rebuild apenas da data afetada e das derivações necessárias.
2. Alterar dado do mês atual e verificar atualização imediata.
3. Alterar dado do mês anterior e verificar atualização imediata.
4. Alterar projeção futura e verificar atualização imediata do cashflow.
5. Filtrar intervalos curtos e longos e validar performance consistente.

## 11. Testes de performance

Medir antes e depois:
- `/dashboard/overview`
- `/reports/overview`
- `/cashflow/overview`

Cenários:
- 7 dias
- 30 dias
- 90 dias
- 1 ano
- multi-ano

## 12. Testes de consistência

Validar que:
- live não espera TTL para refletir mudança
- histórico reflete correção retroativa sem rebuild global desnecessário
- filtros por data retornam o mesmo resultado tanto em faixa live quanto histórica

---

## Resumo executivo

### Como deve funcionar
- histórico: materializado por dia no banco
- live: agregado por dia com entrega rápida via Redis
- filtros por data: consolidação de dias, não rebuild mensal
- alteração histórica: rebuild granular por dia afetado
- alteração live: invalidação imediata + recompute imediato

### O que não recomendo como arquitetura principal
- depender só de snapshot mensal
- depender de TTL do Redis para refletir atualização
- recalcular DRE e cashflow completos a cada leitura

### O que recomendo
- materialização diária como base
- Redis para janelas quentes
- rebuild incremental por data
- carry-forward somente onde realmente necessário
