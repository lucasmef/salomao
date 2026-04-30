# Handoff UI/Layout - Codex - 2026-04-30

## Objetivo deste arquivo

Resumo operacional do que foi implementado no frontend do Gestor Financeiro para que o Claude Code continue do ponto correto, sem reconstruir contexto.

## Estado atual

Branch de trabalho: `dev`

Ultimo commit no momento deste handoff:

- `449495c Redesign overview dashboard layout`

Todos os pushes recentes para `dev` passaram no workflow `Deploy Dev`.

## O que foi entregue

### 1. Fundacao de UI

Criada uma biblioteca interna em `frontend/src/components/ui/` com:

- `Button`
- `Card`
- `Field`
- `Input`
- `Select`
- `Modal`
- `EmptyState`
- `ErrorState`
- `ErrorBoundary`
- `Sparkline`
- `KpiCard`
- `StatusPill`
- `Badge`
- `PeriodChips`
- `index.ts` com barrel export

Tambem foram adicionados tokens e extensoes de design em `frontend/src/styles.css`.

## 2. App shell novo

`frontend/src/components/AppShell.tsx`

Foi implementado um shell novo em duas linhas, com:

- nav principal em pills
- status pill
- busca global
- CTA de novo lancamento
- drawer mobile
- badges por secao

`App.tsx` tambem ja foi ajustado para usar esse shell e `ErrorBoundary`.

## 3. Login migrado para a nova UI

Arquivos:

- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/pages/LoginPage.css`

Feito:

- troca de campos e botoes para `Input`, `Field` e `Button`
- remocao de estilos inline do fluxo MFA
- remocao do import duplicado de fontes
- limpeza de elementos visuais decorativos que nao seguiam o padrao atual

Commit relacionado:

- `26dd26d Migrate login form to UI primitives`

## 4. Tabelas compactas padronizadas

Arquivos:

- `frontend/src/styles/components.css`
- `frontend/src/styles/pages.css`

Feito:

- criados utilitarios compartilhados:
  - `table-shell--scroll`
  - `erp-table--compact`
  - `erp-table--responsive`
  - `col-hide-md`
  - `col-hide-sm`
- adicionada variante `data-mobile-width="compact"` para tabelas menores
- parte do CSS duplicado de tabelas foi removida de `pages.css`

Commits relacionados:

- `13d0150 Standardize compact table utilities`
- `8c9cfdd Apply compact table utilities to open items`

## 5. EntriesPage parcialmente migrada

Arquivo:

- `frontend/src/pages/EntriesPage.tsx`

Feito:

- tabela principal de lancamentos passou a usar:
  - `table-shell--scroll`
  - `erp-table--compact`
  - `erp-table--responsive`
  - `col-hide-md` na coluna `Conta`
- toolbar/filtros avancados migrados parcialmente para `ui`:
  - campo de busca com `Input`
  - selects nativos com `Select as UiSelect`
  - botoes de lote com `Button`
  - botao `Aplicar filtros` com `Button`

O que NAO foi migrado ainda em `EntriesPage`:

- modais de lancamento, transferencia e baixa
- botoes/menus de linha
- popovers internos de periodo e filtro de categoria
- formularios principais ainda usam muitos inputs/selects antigos

Commit relacionado:

- `aa184c5 Migrate entries filters to UI primitives`

## 6. Dashboard novo em /overview/resumo

Arquivo principal:

- `frontend/src/pages/OverviewSectionPage.tsx`

Arquivo novo:

- `frontend/src/pages/OverviewSectionPage.module.css`

Feito:

- a tela antiga foi substituida por um dashboard realmente novo, sem depender do layout herdado de `entries`
- toolbar nova com:
  - `PeriodChips`
  - refresh
  - range personalizado com `Input`
- hero principal de caixa consolidado
- grid de KPIs com `KpiCard`
- comparativo de receita com `RevenueComparisonChart`
- leitura do DRE com `BarChart`
- cards de saldos por conta
- cards de vencidos a pagar e a receber
- card de aniversariantes da semana
- estados vazios com `EmptyState`

Importante:

- a rota correta para esse dashboard e `/overview/resumo`
- o componente usado na navegacao nova e `OverviewSectionPage`, nao `OverviewPage`

Commit relacionado:

- `449495c Redesign overview dashboard layout`

## Commits relevantes em ordem

- `3485e7d Fix Banco Inter refresh syntax`
- `26dd26d Migrate login form to UI primitives`
- `13d0150 Standardize compact table utilities`
- `8c9cfdd Apply compact table utilities to open items`
- `aa184c5 Migrate entries filters to UI primitives`
- `449495c Redesign overview dashboard layout`

## Deploy/dev

Houve uma falha anterior de `Deploy Dev` que nao era causada pelo layout. A causa foi um `SyntaxError` backend em:

- `backend/app/services/inter.py`

Ja corrigido no commit:

- `3485e7d Fix Banco Inter refresh syntax`

Tambem foram mantidos dois commits de diagnostico no script de deploy:

- `77276f5 Improve dev deploy healthcheck diagnostics`
- `a9cc283 Avoid interactive sudo in deploy diagnostics`

## O que ainda falta

### Onda 4 ainda nao terminou de verdade

Ela foi parcialmente coberta, mas ainda falta a migracao operacional mais pesada da tela de lancamentos:

- finalizar `EntriesPage`
- trocar os formularios/modais principais para os componentes da `ui`
- remover mais classes antigas e estilos ad-hoc da pagina
- se possivel, comecar a quebrar parte do CSS dessa tela para modulo ou pelo menos isolar melhor os blocos

### Onda 5 ainda pode continuar

A linha que foi iniciada foi padronizacao de tabelas em outras paginas. Proximos candidatos naturais:

- `BillingPage.tsx`
- `BoletosPage.tsx`
- `ReconciliationPage.tsx`

Prioridade tecnica:

1. continuar a reduzir CSS duplicado de tabela em `pages.css`
2. trocar regras mobile baseadas em `nth-child` por classes utilitarias quando isso for seguro
3. aplicar `erp-table--compact` / `erp-table--responsive` progressivamente

## Sugestao de proximo passo para Claude

Sequencia recomendada:

1. abrir `frontend/src/pages/EntriesPage.tsx`
2. concluir a migracao dos modais e formularios dessa tela para `ui`
3. validar `npm run typecheck`
4. validar `npm run build`
5. push em `dev` e acompanhar `Deploy Dev`

Depois disso:

1. pegar `BillingPage.tsx`
2. aplicar os utilitarios de tabela compartilhados
3. remover regras redundantes correspondentes de `pages.css`

## Observacoes importantes

- Nao usar `OverviewPage.tsx` como referencia do dashboard novo; a tela ativa e `OverviewSectionPage.tsx`
- O shell novo ja esta em producao no `dev`
- Os deploys recentes do `dev` estao verdes
- O repo estava limpo no momento deste handoff
