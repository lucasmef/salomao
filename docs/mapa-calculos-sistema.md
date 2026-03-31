# Mapa de Calculos do Sistema

Este documento resume como os valores sao calculados hoje no backend do sistema, quais campos servem de base e quais modulos consomem cada numero.

## Campos-base

- `opening_balance` (saldo inicial): saldo inicial cadastrado na conta.
- `principal_amount` (valor principal): principal do lancamento.
- `interest_amount` (juros): juros.
- `penalty_amount` (multa): multa.
- `discount_amount` (desconto): desconto.
- `total_amount` (valor total): valor total do lancamento.
- `paid_amount` (valor pago/recebido): valor efetivamente pago ou recebido.
- `status` (situacao do lancamento): `planned`, `partial`, `settled` ou `cancelled`.
- `settled_at` (data de quitacao): data/hora em que o lancamento foi quitado.
- `entry_type` (natureza do lancamento): `income`, `expense`, `transfer`, `historical_receipt`, `historical_purchase`, `historical_purchase_return`, `adjustment`.

## 1. Lancamentos Financeiros

Arquivo principal: `backend/app/services/finance_ops.py`

### 1.1 Cadastro e edicao manual

- Em criacao/edicao manual, o backend grava `total_amount` (valor total) exatamente como vier do payload.
- O valor pago acumulado fica em `paid_amount` (valor pago/recebido).
- A listagem de lancamentos retorna dois totais brutos:
  - `total_amount = soma(total_amount)`
    `total_amount` aqui significa soma do valor bruto dos lancamentos filtrados.
  - `paid_amount = soma(paid_amount)`
    `paid_amount` aqui significa soma do que ja foi pago/recebido nos lancamentos filtrados.
- Esses totais da listagem nao representam saldo; sao apenas agregados de grade.

### 1.2 Baixa de lancamento

Funcao: `apply_settlement_breakdown`

- Formula de caixa da baixa:
  - `cash_total = principal + interest + penalty - discount`
    `cash_total` = valor financeiro final da baixa.
    `principal` = valor principal final.
    `interest` = juros.
    `penalty` = multa.
    `discount` = desconto.
- Regras:
  - `principal > 0`
  - `cash_total > 0`
  - `paid_amount` (valor ja pago) nao pode ficar maior que o principal final.
- Depois da baixa:
  - o lancamento principal fica com `principal_amount = principal`
    `principal_amount` = principal do titulo apos a baixa.
  - `interest_amount`, `penalty_amount` e `discount_amount` do lancamento principal sao zerados
    esses campos representam juros, multa e desconto armazenados no titulo principal.
  - `total_amount` do lancamento principal passa a ser igual ao principal
    `total_amount` = novo valor total do titulo principal.
  - juros, multa e desconto viram lancamentos separados do tipo despesa, todos liquidados
  - `paid_amount` do lancamento principal vira `total_amount`
    `paid_amount` = valor efetivamente quitado do principal.
  - `status = settled`
    `settled` = liquidado.

### 1.3 Estorno / reabertura

- `reverse_entry` reabre o lancamento:
  - `status = planned`
    `planned` = em aberto.
  - `paid_amount = 0`
    `paid_amount` = zera o valor pago.
  - `settled_at = null`
    `settled_at` = remove a data de quitacao.

## 2. Transferencias

Arquivo principal: `backend/app/services/finance_ops.py`

### 2.1 Criacao

Funcao: `create_transfer`

- Cada transferencia cria:
  - 1 registro em `transfers`
  - 1 lancamento de saida na conta origem
  - 1 lancamento de entrada na conta destino
- As duas pernas recebem:
  - `entry_type = transfer`
    `entry_type` = natureza do lancamento; aqui significa transferencia interna.
  - mesmo `total_amount`
    `total_amount` = valor total da transferencia.
  - mesmo `paid_amount` quando `status = settled`
    `paid_amount` = valor ja realizado da transferencia.
  - mesmo `due_date/competence_date/issue_date`
    `due_date` = vencimento.
    `competence_date` = competencia.
    `issue_date` = emissao/origem.

### 2.2 Efeito contabil no caixa

- Conta origem: reduz saldo pelo valor pago/realizado.
- Conta destino: aumenta saldo pelo valor pago/realizado.
- Consolidado da empresa: efeito liquido zero.

## 3. Recorrencias e Emprestimos

Arquivo principal: `backend/app/services/finance_ops.py`

### 3.1 Recorrencias

Funcao: `generate_recurrence_entries`

- Para cada ocorrencia gerada:
  - `principal = principal_amount do rule ou amount`
    `principal_amount` = principal configurado na recorrencia.
    `amount` = valor base da regra.
  - `total_amount = principal + interest + penalty - discount`
    `total_amount` = valor total do lancamento recorrente.
- Os lancamentos nascem como `planned` (`planned` = em aberto).

### 3.2 Emprestimos

Funcao: `create_loan_contract`

- Parcelamento do contrato:
  - `principal_installment = principal_total / installments_count`
    `principal_installment` = principal de cada parcela.
    `principal_total` = principal total do contrato.
    `installments_count` = quantidade de parcelas.
  - `interest_installment = interest_total / installments_count`
    `interest_installment` = juros por parcela.
    `interest_total` = juros total do contrato.
  - ambos arredondados em 2 casas
- A ultima parcela absorve o residual do arredondamento:
  - `principal ultimo = remaining_principal`
    `remaining_principal` = principal que sobrou apos o rateio.
  - `interest ultimo = remaining_interest`
    `remaining_interest` = juros que sobraram apos o rateio.
- Cada parcela gera:
  - 1 `FinancialEntry`
  - 1 `LoanInstallment`

## 4. Fluxo de Caixa

Arquivo principal: `backend/app/services/cashflow.py`

### 4.1 Saldo atual por conta

Funcao: `_current_balance_for_account`

#### Contas normais

- Formula:
  - `saldo_atual = opening_balance + realizados_de_entrada - realizados_de_saida +/- transferencias_realizadas`
    `opening_balance` = saldo inicial da conta.
- O que entra como realizado:
  - se `paid_amount > 0`, usa `paid_amount`
    `paid_amount` = valor realmente pago/recebido.
  - senao, se `status == settled`, usa `total_amount`
    `status` = situacao do lancamento.
    `settled` = liquidado.
    `total_amount` = valor total do lancamento.
  - caso contrario, nao entra no saldo
- Regras por tipo:
  - `income`: soma
    `income` = receita/entrada.
  - `expense`: subtrai
    `expense` = despesa/saida.
  - `transfer` origem: subtrai
    `transfer` = transferencia interna.
  - `transfer` destino: soma
- Conciliacao e extrato bancario nao entram na formula do saldo atual.

#### Conta de controle de recebiveis

- Conta especial `receivables_control` (conta de controle de recebiveis).
- Formula:
  - `saldo = soma(restante a receber)`
  - `restante = total_amount - paid_amount`
    `total_amount` = valor total do titulo de controle.
    `paid_amount` = valor ja baixado/recebido.
- Usa apenas lancamentos do `source_system = linx_sales_control`
  `source_system` = origem tecnica do lancamento.

### 4.2 Eventos futuros

Funcao: `_future_events`

- Entram na projecao:
  - titulos a receber do LINX ainda abertos
  - lancamentos `planned/partial` com `remaining_amount = total_amount - paid_amount`
    `remaining_amount` = saldo ainda nao realizado do lancamento.
  - transferencias futuras:
    - origem vira `outflow`
      `outflow` = saida projetada.
    - destino vira `inflow`
      `inflow` = entrada projetada.
  - parcelas de compras ainda abertas quando `include_purchase_planning = True`
    `include_purchase_planning` = indicador para incluir compras planejadas na projecao.

### 4.3 Projecoes diaria, semanal e mensal

Funcao: `build_cashflow_overview`

- Saldo inicial da projecao = `current_balance`
  `current_balance` = saldo atual consolidado antes dos eventos futuros.
- Para cada bucket:
  - `closing_balance = opening_balance + inflows - outflows`
    `closing_balance` = saldo de fechamento do periodo.
    `opening_balance` = saldo de abertura do periodo.
    `inflows` = entradas projetadas.
    `outflows` = saidas projetadas.
  - o fechamento de um periodo vira a abertura do proximo
- Totais do periodo:
  - `projected_inflows = soma(inflows diarios)`
    `projected_inflows` = total projetado de entradas.
  - `projected_outflows = soma(outflows diarios)`
    `projected_outflows` = total projetado de saidas.
  - `projected_ending_balance = closing_balance do ultimo dia`
    `projected_ending_balance` = saldo final projetado.

## 5. DRE e DRO

Arquivo principal: `backend/app/services/reports.py`

### 5.1 DRE

Funcao: `_build_dre`

#### Receita e CMV

- A DRE usa `SalesSnapshot` (snapshot de faturamento).
- O codigo hoje calcula:
  - `gross_revenue += snapshot.gross_revenue - snapshot.discount_or_surcharge`
    `gross_revenue` = receita bruta acumulada no relatorio.
    `snapshot.gross_revenue` = receita do snapshot.
    `snapshot.discount_or_surcharge` = descontos/acrescimos do snapshot.
  - `deductions += snapshot.discount_or_surcharge`
    `deductions` = deducoes de vendas acumuladas.
  - `net_revenue += snapshot.gross_revenue`
    `net_revenue` = receita liquida acumulada, conforme o codigo atual.
- `cmv` vem de markup:
  - `cmv = net_revenue_snapshot / (1 + markup/100)`
    `cmv` = custo das mercadorias vendidas.
    `net_revenue_snapshot` = receita usada como base no snapshot.
    `markup` = markup importado.

#### Despesas e resultado

- Entradas operacionais adicionais entram por `FinancialEntry` de receita fora do historico de caixa.
- Despesas entram por componentes do lancamento.
- Regra de competencia:
  - usa `principal_amount`, com fallback para `total_amount`
    `principal_amount` = componente principal do lancamento.
    `total_amount` = valor total do lancamento.
- Formulas:
  - `gross_profit = net_revenue - cmv`
    `gross_profit` = lucro bruto.
  - `operating_result = gross_profit + other_operating_income - operating_expenses - financial_expenses`
    `operating_result` = resultado operacional.
    `other_operating_income` = outras receitas operacionais.
    `operating_expenses` = despesas operacionais.
    `financial_expenses` = despesas financeiras.
  - `non_operating_result = non_operating_income - non_operating_expenses`
    `non_operating_result` = resultado nao operacional.
    `non_operating_income` = receitas nao operacionais.
    `non_operating_expenses` = despesas nao operacionais.
  - `profit_before_tax = operating_result + non_operating_result`
    `profit_before_tax` = lucro antes dos impostos.
  - `net_profit = profit_before_tax - taxes_on_profit`
    `net_profit` = lucro liquido.
    `taxes_on_profit` = impostos/provisoes sobre o lucro.
  - `remaining_profit = net_profit - profit_distribution`
    `remaining_profit` = lucro remanescente.
    `profit_distribution` = lucro distribuido.

### 5.2 DRO

Funcao: `_build_dro`

- A DRO usa regime de caixa.
- Para receitas:
  - usa `paid_amount` quando houver
    `paid_amount` = valor efetivamente recebido.
  - senao usa `total_amount`
    `total_amount` = valor total do titulo.
- Para despesas:
  - usa `paid_amount` no componente principal
    `paid_amount` = valor efetivamente pago.
  - se `paid_amount == 0` e `status == settled`, usa `total_amount`
    `status` = situacao do lancamento.
    `settled` = liquidado.
    `total_amount` = valor total do titulo.
- Transferencias nao entram na DRO.

Formulas:

- `contribution_margin = operating_revenue - sales_taxes - purchases_paid`
  `contribution_margin` = margem de contribuicao.
  `operating_revenue` = receita operacional em caixa.
  `sales_taxes` = impostos sobre vendas.
  `purchases_paid` = compras pagas.
- `operating_result = contribution_margin - operating_expenses - financial_expenses`
  `operating_result` = resultado operacional da DRO.
- `non_operating_result = non_operating_income - non_operating_expenses`
  `non_operating_result` = resultado nao operacional da DRO.
- `net_profit = operating_result + non_operating_result`
  `net_profit` = lucro liquido da DRO.
- `remaining_profit = net_profit - profit_distribution`
  `remaining_profit` = lucro remanescente apos distribuicao.

## 6. Dashboard

Arquivo principal: `backend/app/services/dashboard.py`

- O dashboard nao recalcula fundamentos; ele consome:
  - `build_reports_overview`
  - `build_cashflow_overview`
- KPIs principais:
  - `gross_revenue`, `net_revenue`, `cmv`, `operating_expenses`, `financial_expenses`, `net_profit`, `profit_distribution`, `remaining_profit` vem da DRE
    `gross_revenue` = receita bruta.
    `net_revenue` = receita liquida.
    `cmv` = custo das mercadorias vendidas.
    `operating_expenses` = despesas operacionais.
    `financial_expenses` = despesas financeiras.
    `net_profit` = lucro liquido.
    `profit_distribution` = lucro distribuido.
    `remaining_profit` = lucro restante.
  - `purchases_paid` vem da DRO
    `purchases_paid` = compras pagas.
  - `current_balance` e `projected_balance` vem do cashflow
    `current_balance` = saldo atual.
    `projected_balance` = saldo projetado no fim do periodo.
  - `overdue_payables` e `overdue_receivables` contam lancamentos `planned/partial` vencidos
    `overdue_payables` = contas a pagar vencidas.
    `overdue_receivables` = contas a receber vencidas.
  - `pending_reconciliations` conta movimentos bancarios ainda sem conciliacao
    `pending_reconciliations` = extratos pendentes de conciliacao.

## 7. Conciliacao Bancaria

Arquivo principal: `backend/app/services/reconciliation.py`

### 7.1 Score de sugestao

Funcao: `_score_candidate`

Pontuacao por fatores:

- valor exato ou proximo
- proximidade de data
- mesma conta
- mesma natureza (`income`/`expense`)
- similaridade textual
- regra salva de conciliacao

### 7.2 Conciliacao efetiva

Funcao: `create_reconciliation`

- Caso 1 extrato x 1 lancamento:
  - permite ajuste manual de principal/juros/multa/desconto
  - exige fechamento exato entre extrato e `cash_total`
    `cash_total` = valor financeiro final da baixa.
- Caso multiplo:
  - exige `soma extrato == soma saldo aberto dos lancamentos`
  - cada lancamento precisa ser quitado integralmente
- Ao conciliar:
  - `paid_amount = total_amount`
    `paid_amount` = valor pago/recebido apos conciliacao.
    `total_amount` = valor total do lancamento.
  - `status = settled`
    `settled` = liquidado.
  - `settled_at = maior posted_at aplicado`
    `posted_at` = data do movimento bancario no extrato.

### 7.3 Desconciliacao

Funcao: `_apply_unreconciled_status`

- `new_paid = paid_amount - amount_to_remove`
  `new_paid` = novo valor pago depois de remover a conciliacao.
  `amount_to_remove` = valor retirado da conciliacao.
- Regras:
  - `new_paid <= 0` -> `planned`
  - `0 < new_paid < total_amount` -> `partial`
  - `new_paid >= total_amount` -> `settled`
    `partial` = parcialmente pago/recebido.

## 8. Planejamento de Compras

Arquivo principal: `backend/app/services/purchase_planning.py`

### 8.1 Totais por linha

Funcao: `build_purchase_planning_overview`

Cada linha agrega por `marca + colecao`.

Campos:

- `purchased_total` (total comprado): soma de `PurchasePlan.purchased_amount`
- `delivered_total` (total entregue): soma de `PurchaseDelivery.amount`
- `launched_financial_total` (total financeiro lancado): soma de `FinancialEntry.total_amount` ligados a fornecedor/colecao/nota/parcela
- `paid_total` (total pago): soma de `FinancialEntry.paid_amount` desses mesmos lancamentos
- `outstanding_goods_total = max(purchased_total - delivered_total, 0)`
  `outstanding_goods_total` = mercadoria ainda nao entregue.
- `delivered_not_recorded_total = max(delivered_total - launched_financial_total, 0)`
  `delivered_not_recorded_total` = entregue que ainda nao virou financeiro.

### 8.2 Parcelas e contas a pagar projetadas

- Saldo aberto da parcela:
  - `remaining_amount = max(installment.amount - linked_entry.paid_amount, 0)`
    `remaining_amount` = saldo em aberto da parcela.
- `outstanding_payable_total` da linha:
  - `outstanding_payable_total` = total ainda a pagar projetado para a linha.
  - parcelas abertas reais
  - mais projecao simulada do que ainda falta receber fisicamente

### 8.3 Projecao mensal de compras

- `planned_outflows` (saidas planejadas): soma do aberto por mes
- `linked_payments` (pagamentos vinculados): soma de `financial_entry.paid_amount` ligado as parcelas
- `open_balance = planned_outflows - linked_payments`
  `open_balance` = saldo aberto projetado do mes.

## 9. Importacoes

Arquivo principal: `backend/app/services/imports.py`

### 9.1 Faturamento Linx

- Importa `SalesSnapshot` (snapshot de faturamento).
- Para cartao e pix cria/atualiza lancamentos de controle:
  - conta `receivables_control` (conta de controle de recebiveis)
  - `entry_type = income`
    `income` = entrada/receita.
  - `total_amount = receita do metodo`
    `total_amount` = total a receber por cartao ou pix.
  - `paid_amount` preservado ate o limite do novo total
    `paid_amount` = valor ja recebido/baixado.

### 9.2 OFX

- Nao altera saldo atual sozinho.
- Apenas grava `BankTransaction` para posterior conciliacao.

### 9.3 Livro caixa historico

- Classifica linhas por palavras-chave:
  - compra
  - devolucao de compra
  - transferencia
  - ajuste
  - recebimento historico
  - despesa financeira
- Tudo entra como `status = settled` numa conta historica inativa.
  `settled` = liquidado.

## 10. Boletos

Arquivo principal: `backend/app/services/boletos.py`

- `receivable_total = soma(amount)` dos titulos a receber ainda abertos
  `receivable_total` = total financeiro das faturas abertas.
  `amount` = valor da fatura.
- `boleto_count = quantidade de boletos importados`
  `boleto_count` = total de boletos carregados.
- `overdue_boleto_count = quantidade de casos classificados como boleto vencido`
  `overdue_boleto_count` = total de boletos vencidos/em atraso.
- `paid_pending_count = quantidade de casos em que banco informa pago, mas LINX ainda esta aberto`
  `paid_pending_count` = pagos no banco, pendentes no LINX.
- `missing_boleto_count = quantidade de casos sem boleto correspondente`
  `missing_boleto_count` = faturas sem boleto correspondente.

O dashboard de boletos cruza:

- faturas abertas do LINX
- boletos importados de Inter/C6
- configuracao por cliente
- matching individual ou agrupado por mes/competencia

## 11. Pontos de Atencao

### 11.1 DRE depende da semantica de `discount_or_surcharge`

- O codigo assume uma relacao especifica entre `gross_revenue` e `discount_or_surcharge`.
  `discount_or_surcharge` = descontos/acrescimos importados no snapshot.
- Vale validar com dado real se `Receita Bruta`, `Deducoes` e `Receita Liquida` estao com os sinais corretos.

### 11.2 Parcial no regime de caixa nao tem data propria de pagamento parcial

- Quando o lancamento esta `partial` e nao ha `settled_at`, a DRO usa `due_date` como referencia de caixa.
  `partial` = parcialmente pago/recebido.
  `due_date` = vencimento.
- Se for importante apurar caixa pela data real de cada pagamento parcial, hoje o modelo ainda nao guarda essa granularidade.

### 11.3 Transferencias historicas antigas nao estao normalizadas no modelo novo

- O legado historico tem muitos lancamentos tipo `transfer` sem registro na tabela `transfers`.
- Eles ficam isolados na conta historica inativa, mas estruturalmente nao seguem o padrao novo de duas pernas vinculadas.
