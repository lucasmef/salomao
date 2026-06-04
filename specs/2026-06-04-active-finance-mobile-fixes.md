# Active finance and mobile fixes

## Metadata

- Status: review
- Mode: bugfix
- Complexity: high
- Created: 2026-06-04
- Updated: 2026-06-04

## Objective

Corrigir os itens ativos ID 001 a ID 010 com foco em seguranca financeira, consistencia dos lancamentos e usabilidade mobile em celular real. O PR deve ser pequeno, validavel e sem refatoracao ampla fora do escopo.

## Context

- Projeto ERP/backoffice financeiro com dados reais; financeiro, conciliacao, compras e boletos sao areas sensiveis.
- Backend: FastAPI, SQLAlchemy 2, pytest; logica de baixa fica em `backend/app/services/finance_ops.py`.
- Frontend: React, TypeScript, Vite; tela de Lancamentos ja tem padrao compacto validado em `entries-list-table--compact`.
- Spec relacionada: `specs/2026-06-03-mobile-tables-usability.md`, que consolidou a auditoria mobile e definiu layout compacto ate 480px.
- Baixa com credito de devolucao ja usa `penalty_mode="return_credit"` e gera ajuste `settlement_adjustment`; a falha ativa e permitir valor liquido zero/parcial e preservar saldo liquido correto na conta.

## Scope

- [x] ID 001: permitir baixa/faturamento em lote de lancamentos sem conta, com modal para escolher conta, revisar valores e confirmar.
- [x] ID 002: permitir credito de devolucao parcial/total na baixa de faturas de fornecedor, inclusive valor liquido zero.
- [x] ID 003: layout compacto mobile para tabelas de Conciliacao.
- [x] ID 004: layout compacto mobile para Cobranca > Boletos/Faturas.
- [x] ID 005: layout compacto mobile para Movimentos.
- [x] ID 006: layout compacto mobile para Produtos.
- [x] ID 007: layout compacto mobile para Clientes.
- [x] ID 008: layout compacto mobile para Faturas a receber, Contas e Categorias.
- [x] ID 009: affordance visual de scroll na sub-navegacao por abas.
- [x] ID 010: reutilizar padrao compacto sem quebrar `.erp-table`, `.table-shell` e desktop/tablet fora do escopo.

## Out of scope

- Migracoes de schema/API sem necessidade clara.
- Biblioteca nova de tabela.
- Redesign amplo de desktop.
- Deploy em VPS ou promocao para producao.
- Reabrir itens mobile ja confirmados como OK fora da lista ativa.

## Grill Gate

Decision: not_needed

Reason:
O usuario definiu regras, criterios, ordem e cuidados. A spec mobile anterior ja teve Grill Gate respondido: usar padrao compacto de Lancamentos, breakpoint `max-width: 480px`, e tratar Boletos/Faturas dentro do redesenho compacto. A decisao financeira inferida do criterio e registrar saida total da fatura e entrada do credito na mesma conta, deixando o saldo liquido correto.

Questions, if any:
1. N/A

Answers:
1. N/A

## Acceptance criteria

- [ ] Lote com faturas com conta baixa normalmente.
- [ ] Lote com faturas sem conta abre modal, exige conta e aplica a conta escolhida antes da baixa.
- [ ] Lote misto aplica conta escolhida apenas onde faltar conta e confirma valores principais antes da execucao.
- [ ] Baixa de fatura de R$ 1.000 com credito R$ 800 gera impacto liquido de R$ 200 na conta.
- [ ] Baixa de fatura de R$ 1.000 com credito R$ 1.000 e permitida e gera impacto liquido R$ 0 na conta.
- [ ] Credito maior que a fatura e bloqueado.
- [ ] Operacao registra fatura de saida total e entrada de credito de devolucao, com rastreabilidade por fornecedor/fatura/documento.
- [ ] Em viewport 390px, telas alvo mostram identificacao e valor/saldo essenciais sem scroll horizontal.
- [ ] Sub-navegacao mobile deixa perceptivel que existem mais abas/opcoes.
- [ ] Typecheck e build frontend passam.
- [ ] Testes backend relevantes passam.
- [ ] Screenshots mobile antes/depois ficam em `specs/artifacts/2026-06-04-active-finance-mobile-fixes/` e copias globais em `G:\Meu Drive\.agentes`.

## Implementation plan

- [x] Atualizar testes financeiros para credito parcial, total e maior que a fatura.
- [x] Ajustar `apply_settlement_breakdown`/`settle_entry` para permitir valor liquido zero apenas com `return_credit`, mantendo rastreabilidade e saldo liquido correto.
- [x] Ajustar tela de Lancamentos para lote com modal de conta/confirmacao em vez de bloqueio por falta de conta.
- [x] Adicionar padrao compacto reutilizavel em CSS escopado a telas alvo ate `480px`.
- [x] Aplicar classes/atributos nas tabelas alvo: Conciliacao, Boletos/Faturas, Movimentos, Produtos, Clientes, Faturas a receber, Contas, Categorias.
- [x] Adicionar affordance visual de scroll na sub-navegacao mobile.
- [x] Rodar validacoes backend/frontend e browser mobile/desktop com screenshots.
- [x] Atualizar esta spec com arquivos, resultados, riscos e evidencias.

## Progress

- 2026-06-04 - Lidas as skills BuilderFlow e gestor-financeiro-workflow.
- 2026-06-04 - Lidos `AGENTS.md`, `docs/CONTEXT.md`, `docs/ADR.md`, `PLANS.md` e spec mobile anterior.
- 2026-06-04 - Identificado bloqueio frontend no lote por `selectedSettleBlockedCount`.
- 2026-06-04 - Identificada regra backend que bloqueia `cash_total <= 0` e credito de devolucao sem conta.
- 2026-06-04 - Backend financeiro ajustado; testes financeiros alvo passaram.
- 2026-06-04 - Baixa em lote alterada para abrir modal de revisao e conta para itens sem conta.
- 2026-06-04 - Tabelas alvo receberam `mobile-compact-table` e `data-label` com CSS em `max-width: 480px`.
- 2026-06-04 - Typecheck e build frontend passaram.
- 2026-06-04 - Browser plugin indisponivel; fallback Playwright usado para screenshots de prova CSS. Validacao real com backend local ficou bloqueada porque uvicorn travou em startup.

## Decisions

- Decision: tratar os 10 IDs em uma spec viva unica para esta rodada.
  Reason: o pedido do usuario agrupa os itens em uma entrega priorizada e a spec mobile anterior agora vira contexto.
  ADR needed: no
- Decision: vincular o credito de devolucao gerado na baixa a mesma conta da fatura.
  Reason: atende ao criterio de registrar saida total e entrada do abatimento, mantendo impacto liquido correto na conta.
  ADR needed: no
- Decision: permitir `cash_total == 0` apenas quando `penalty_mode == "return_credit"`.
  Reason: baixa total por credito deve ser permitida, mas outras baixas com valor final zero continuam protegidas.
  ADR needed: no

## Files changed

- `backend/app/services/finance_ops.py` - regra de baixa com credito de devolucao e ajuste de conta do credito.
- `backend/tests/test_financial_calculations.py` - regressao para credito parcial, total e excesso.
- `frontend/src/pages/EntriesPage.tsx` - modal de revisao de baixa em lote e aplicacao de conta para itens sem conta.
- `frontend/src/styles/pages.css` - padrao `mobile-compact-table`, estilos do modal de revisao e affordance de tabs.
- `frontend/src/pages/ReconciliationPage.tsx` - tabelas de extrato/lancamentos marcadas para compacto mobile.
- `frontend/src/pages/BillingPage.tsx` - tabelas de Faturas e Boletos marcadas para compacto mobile.
- `frontend/src/pages/BoletosPage.tsx` - tabelas principais legadas de faturas/boletos marcadas para compacto mobile.
- `frontend/src/pages/CadastrosMovementsPage.tsx` - tabela marcada para documento/produto/valor/data mobile.
- `frontend/src/pages/CadastrosProductsPage.tsx` - tabela marcada para descricao/venda/saldo mobile.
- `frontend/src/pages/CadastrosClientsPage.tsx` - tabela marcada para nome/documento/cidade mobile.
- `frontend/src/pages/CadastrosOpenReceivablesPage.tsx` - tabela marcada para identificacao/valor mobile.
- `frontend/src/pages/FinanceOpenItemsPage.tsx` - tabela marcada para titulo/saldo mobile.
- `frontend/src/pages/MasterDataPage.tsx` - tabelas de Contas e Categorias marcadas para compacto mobile.

## Validation

Commands run:

- [x] `cd backend; $env:PYTHONPATH='.'; uv run pytest tests/test_financial_calculations.py -q`
- [x] `cd backend; uv run ruff check app/services/finance_ops.py tests/test_financial_calculations.py`
- [x] `cd frontend; npm run typecheck`
- [x] `cd frontend; npm run build`

Results:

- `pytest tests/test_financial_calculations.py -q`: passed, 26 tests.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- `ruff check app/services/finance_ops.py tests/test_financial_calculations.py`: failed due existing E501 legacy lint debt in touched files. New long lines added in this task were wrapped; remaining failures include pre-existing lines such as `finance_ops.py:114`, `finance_ops.py:159`, `finance_ops.py:168`, `test_financial_calculations.py:844`.
- Local backend validation: blocked. `uvicorn` with `APP_MODE=local`, `.env.local`, and `BACKUP_ON_STARTUP=false` stayed at `Waiting for application startup`; port 8000 never opened. Logs saved in artifacts.
- Local frontend server: started on 127.0.0.1:5173 and stopped after validation.

Frontend evidence:

- `specs/artifacts/2026-06-04-active-finance-mobile-fixes/01-frontend-mobile-entry.png` - Vite frontend at 390px; blocked at login because backend was unavailable.
- `specs/artifacts/2026-06-04-active-finance-mobile-fixes/02-mobile-compact-reconciliation.png` - CSS proof for reconciliation compact cards.
- `specs/artifacts/2026-06-04-active-finance-mobile-fixes/03-mobile-compact-billing.png` - CSS proof for billing compact cards.
- `specs/artifacts/2026-06-04-active-finance-mobile-fixes/04-mobile-compact-cadastros.png` - CSS proof for cadastros compact cards.
- Global copies: `G:\Meu Drive\.agentes\gestor-financeiro-reconciliation-2026-06-04.png`, `G:\Meu Drive\.agentes\gestor-financeiro-billing-2026-06-04.png`, `G:\Meu Drive\.agentes\gestor-financeiro-cadastros-2026-06-04.png`.

## Risks

- Risk: ajuste em credito de devolucao altera expectativa antiga de `account_id=None` no credito.
  Mitigation: testes devem provar saldo liquido correto na conta e rastreabilidade do ajuste.
- Risk: CSS compacto pode afetar tabelas fora do escopo.
  Mitigation: classes especificas por tela e media query `max-width: 480px`.
- Risk: validacao manual com dados reais pode depender de ambiente local autenticado/seed.
  Mitigation: usar seed equivalente quando dados reais nao estiverem disponiveis e registrar limitacao.
- Risk: validacao visual real nao foi concluida por backend local travado no startup.
  Mitigation: repetir teste manual em dev/VPS ou corrigir startup local antes de merge final; screenshots atuais provam somente o CSS compacto em amostras estaticas.

## Next step

Revisar diff, repetir validacao manual com backend operacional/dados reais, e entao liberar merge.
