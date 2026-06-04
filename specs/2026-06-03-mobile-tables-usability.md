# Usabilidade mobile das tabelas (colunas importantes fora da tela)

## Metadata

- Status: planned (Grill Gate concluído; aguardando autorização para implementar)
- Mode: build
- Complexity: medium
- Created: 2026-06-03
- Updated: 2026-06-03

## Objective

Corrigir a usabilidade das tabelas densas na versão mobile (≤ ~430px), onde as
colunas mais relevantes (valores em R$, saldo, status) ficam fora da tela por
padrão e/ou o layout quebra. A meta é que as informações essenciais de cada
linha fiquem visíveis sem depender de scroll horizontal, replicando o padrão já
existente na tela de Lançamentos.

## Context

- Stack: frontend React + TypeScript + Vite (`frontend/`), CSS próprio (sem
  Tailwind). Tabelas usam a classe base `.erp-table` dentro de wrappers
  `.table-shell` / `.table-shell--scroll`.
- Breakpoint mobile relevante: `@media (max-width: 768px)` em
  `frontend/src/styles/pages.css:5189+`. Nele as tabelas densas recebem
  `overflow-x: auto` com `min-width: max(100%, 640px|720px)` — ou seja, a tabela
  mantém largura de desktop e rola horizontalmente. Nenhuma coluna é escondida
  por `display:none`; o problema é de ordem/layout: colunas importantes ficam à
  direita, fora do viewport na abertura.
- Padrão bom já existente: tela de Lançamentos (`/financeiro/lancamentos`) usa
  toggle Compacto/Conforto e a classe `.entries-list-table--compact`
  (`pages.css:5359`: `width:100%`, `table-layout:fixed`, sem scroll horizontal).
  Mostra título, vencimento, valor e ações sem scroll lateral.
- Auditoria manual feita em iPhone 12 (390×844) com SQLite local + seed demo,
  via Playwright. Evidências em `specs/artifacts/2026-06-03-mobile-tables-usability/`.

### Achados da auditoria (severidade)

🔴 Crítico
- **Conciliação** (`/financeiro/conciliacao`, `ReconciliationPage`): nas duas
  tabelas (extrato e lançamentos) a coluna **Valor** entra parcial/fora da tela.
  Conciliar sem ver o valor inviabiliza a tarefa no mobile.
- **Cobrança › Boletos** (`/financeiro/cobranca/boletos`, `BoletosPage`): layout
  quebrado — `billing-table-shell` com `overflow-x: hidden` (sem scroll), 10
  colunas comprimidas, header com checkbox duplicado e área em branco grande.
  (Efeito agravado por lista vazia no teste; revalidar com dados reais.)

🟠 Alto — valores/medidas fora da tela por padrão (scroll resolve, UX ruim)
- **Movimentos** (`/cadastros/movimentos`, ~1049px): visível só
  Lançamento/Tipo/Documento; fora: Produto, Coleção, Qtd, Vlr. unit., Vlr.
  total, Custo, Natureza, Data.
- **Produtos** (~907px): fora da tela Venda e Saldo (preço de venda e estoque).
- **Clientes** (~1158px): 8 de 11 colunas fora da tela.

🟡 Médio
- **Faturas a receber / Contas / Categorias**: coluna de Valor/Saldo logo após a
  borda direita (parcial), exige scroll.
- **Sub-navegação** (`tabs-container`, ~620px): estoura 390px; alcançável via
  scroll de `.section-navigation`, mas sem afordância visual de scroll.
- **Banner "AMBIENTE DE DESENVOLVIMENTO"** gruda no header no topo do mobile.

✅ Referência a replicar
- Lançamentos: `entries-list-table--compact` + toggle Compacto/Conforto.

## Scope

- [ ] Conciliação: garantir Valor (e Situação/Pago) visíveis sem scroll horizontal no mobile.
- [ ] Movimentos: priorizar valores no mobile (reordenar ou layout compacto).
- [ ] Produtos: trazer Venda e Saldo para a área visível no mobile.
- [ ] Clientes: layout mobile que mostre identificação + documento/cidade essenciais.
- [ ] Cobrança › Boletos/Faturas: corrigir `overflow-x: hidden` do `billing-table-shell` e o header quebrado.
- [ ] Afordância de scroll horizontal (indicador/sombra na borda direita) nas tabelas que mantiverem scroll.
- [ ] Faturas a receber / Contas / Categorias: ajuste de ordem/coluna de valor.
- [ ] Sub-navegação: tornar o scroll de abas perceptível ou colapsar em menu no mobile.

## Out of scope

- Redesign visual amplo do sistema de tabelas em desktop.
- Mudança de stack de UI ou introdução de biblioteca de tabela.
- Alterações de backend / schema / API.
- Banner de ambiente (cosmético; tratar em tarefa separada se necessário).

## Grill Gate

Decision: completed

Reason:
Havia múltiplos caminhos válidos com consequências diferentes de esforço e
consistência visual, afetando UI de várias telas. Perguntas respondidas pelo
usuário em 2026-06-03. Nenhuma mudança arquitetural; nenhum dado/financeiro é
tocado. Entrega atual é apenas a spec (planejamento), sem implementação.

Questions:
1. Abordagem preferida no mobile: (a) padrão compacto de Lançamentos,
   (b) reordenar colunas + scroll, ou (c) híbrido por tela?
2. Largura-alvo do breakpoint mobile: `768px` ou `≤ 480px`?
3. Quais colunas são "essenciais" por tela (devem aparecer sem scroll)?
4. Escopo da primeira entrega?
5. Cobrança/Boletos: corrigir como bug isolado de CSS agora, ou junto do
   redesenho compacto?

Answers:
1. **Padrão compacto (a)** — replicar o layout de Lançamentos
   (`entries-list-table--compact`) em todas as telas alvo: cada linha vira um
   bloco com campos rotulados essenciais, sem scroll horizontal.
2. **≤ 480px (só celular)** — aplicar o tratamento mobile apenas em celulares
   reais; não afetar tablets. O breakpoint vigente de `768px` permanece para os
   ajustes existentes; o novo layout compacto usa `@media (max-width: 480px)`.
3. Colunas essenciais seguem os defaults documentados nos critérios de aceite
   (não houve objeção). Refinar por tela na implementação se necessário.
4. **Apenas spec / planejamento agora.** Sem implementação nesta rodada; a
   ordem de entrega (Conciliação + Boletos → Movimentos/Produtos/Clientes →
   demais) fica registrada para quando a implementação for autorizada.
5. **Junto do redesenho compacto** — Boletos/Faturas entram na mesma abordagem
   compacta, sem fix de CSS avulso antes.

## Acceptance criteria

- [ ] Em viewport de 390px, cada tela listada mostra os campos essenciais da
      linha sem scroll horizontal:
  - Conciliação: data/descrição + **Valor** + situação.
  - Movimentos: documento/produto + **Vlr. total** + data.
  - Produtos: descrição + **Venda** + **Saldo**.
  - Clientes: nome + documento + cidade/UF.
  - Faturas a receber / Contas / Categorias: identificação + **Valor/Saldo**.
- [ ] Cobrança › Boletos e Faturas renderizam header e linhas corretamente no
      mobile (sem checkbox duplicado, sem colunas colapsadas), com dados reais.
- [ ] Onde restar scroll horizontal, há afordância visível indicando mais colunas.
- [ ] `npm run typecheck` e `npm run build` passam.
- [ ] Validação manual no navegador (mobile) com screenshots antes/depois.

## Implementation plan

Abordagem definida: **padrão compacto** (replicar Lançamentos) em
`@media (max-width: 480px)`. Boletos/Faturas incluídos no mesmo redesenho.
Implementação **não autorizada ainda** (entrega atual é só a spec).

Ordem prevista para quando for autorizada:

- [ ] Extrair o padrão compacto de Lançamentos (`entries-list-table--compact`) num utilitário/variante reutilizável para tabelas.
- [ ] Definir os campos essenciais por tela (defaults nos critérios de aceite) e o slot de "Ações".
- [ ] Leva 1 (crítico): Conciliação (extrato + lançamentos, com Valor visível) e Cobrança › Boletos/Faturas (compacto, resolvendo o header quebrado).
- [ ] Leva 2 (alto): Movimentos, Produtos, Clientes.
- [ ] Leva 3 (médio): Faturas a receber, Contas, Categorias + afordância de scroll onde restar tabela; sub-navegação mobile.
- [ ] Validar a cada leva (typecheck/build) + teste manual mobile (≤480px) + screenshots depois.

## Progress

- 2026-06-03 - Auditoria mobile executada (iPhone 12 / 390px) com SQLite local + seed demo, via Playwright.
- 2026-06-03 - Achados consolidados; screenshots salvos em `specs/artifacts/2026-06-03-mobile-tables-usability/`.
- 2026-06-03 - Spec criada (status: planned). Aguardando respostas do Grill Gate antes de implementar.
- 2026-06-03 - Grill Gate respondido: abordagem compacta, breakpoint ≤480px, Boletos no redesenho, entrega atual só planejamento. Spec consolidada.

## Decisions

- Decision: Adotar a tela de Lançamentos como padrão de referência para mobile.
  Reason: padrão responsivo já existente e validado no próprio projeto.
  ADR needed: no
- Decision: Usar layout **compacto** (linha → bloco com campos rotulados) em todas as telas alvo, em vez de reordenar colunas.
  Reason: melhor UX e consistência; decisão do usuário no Grill Gate.
  ADR needed: no
- Decision: Aplicar o novo layout em `@media (max-width: 480px)` (só celular).
  Reason: evitar regressão em tablets; decisão do usuário no Grill Gate.
  ADR needed: no
- Decision: Cobrança › Boletos/Faturas tratados dentro do redesenho compacto (sem fix de CSS isolado).
  Reason: decisão do usuário no Grill Gate.
  ADR needed: no

## Files changed

- Nenhum ainda (apenas spec + artifacts). Implementação pendente.

Provável alvo na implementação:
- `frontend/src/styles/pages.css` - regras de tabela no `@media (max-width: 768px)`.
- `frontend/src/pages/ReconciliationPage.tsx` - layout/ordem mobile.
- `frontend/src/pages/BoletosPage.tsx` / `BillingPage.tsx` - `billing-table-shell`.
- Páginas de Movimentos, Produtos, Clientes, Contas, Categorias, Faturas a receber.

## Validation

Commands run:

- [ ] `cd frontend; npm run typecheck`
- [ ] `cd frontend; npm run build`

Results:

- Pendente (sem implementação ainda).

Frontend evidence (auditoria — estado ATUAL/antes):

- `specs/artifacts/2026-06-03-mobile-tables-usability/01-conciliacao-valor-fora-da-tela.png` — Conciliação: Valor fora da tela.
- `specs/artifacts/2026-06-03-mobile-tables-usability/02-movimentos-valores-fora-da-tela.png` — Movimentos: só Lançamento/Tipo/Documento visíveis.
- `specs/artifacts/2026-06-03-mobile-tables-usability/03-produtos-venda-saldo-fora-da-tela.png` — Produtos: Venda/Saldo fora da tela.
- `specs/artifacts/2026-06-03-mobile-tables-usability/04-boletos-layout-quebrado.png` — Boletos: layout quebrado.
- `specs/artifacts/2026-06-03-mobile-tables-usability/05-lancamentos-padrao-bom-compacto.png` — Lançamentos: padrão compacto (referência).
- `specs/artifacts/2026-06-03-mobile-tables-usability/06-contas-saldo-parcial.png` — Contas: Saldo parcial/cortado.

Ambiente de validação (auditoria):
- Backend uvicorn `127.0.0.1:8000`, frontend Vite `127.0.0.1:5173`, SQLite local
  `backend/.runtime/gestor_financeiro.dev.sqlite3` (`APP_MODE=local`).
- Ambos os servidores foram **encerrados** ao final (portas 8000 e 5173 livres).

## Risks

- Risk: alterar regras de tabela no mobile pode afetar telas não listadas que compartilham `.erp-table`/`.table-shell`.
  Mitigation: usar classes específicas por tela/variante e validar visualmente cada tela tocada.
- Risk: reordenar colunas só no mobile pode confundir quem usa desktop e mobile.
  Mitigation: preferir layout compacto (campos rotulados) a reordenar cabeçalhos.
- Risk: o quebra-layout de Boletos pode ter causa além do CSS (dados/condição vazia).
  Mitigation: revalidar com boletos reais antes de concluir.

## Next step

Spec concluída e Grill Gate respondido. **Implementação não autorizada nesta
rodada** (usuário pediu só planejamento). Quando autorizar, iniciar pela Leva 1
(Conciliação + Cobrança/Boletos) com layout compacto em `@media (max-width:
480px)`, em PR pequeno e verificável na branch `dev`.
