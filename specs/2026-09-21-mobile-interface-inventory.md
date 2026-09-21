# Levantamento sistemático de interface mobile

## Metadata

- Status: complete
- Mode: build
- Complexity: high
- Created: 2026-09-21
- Updated: 2026-09-21

## Objective

Inventariar sistematicamente as telas, com prioridade para celular, e registrar problemas de responsividade, viewport, scroll, interação e tabelas por rota.

## Scope

- [x] SAL-002: levantamento estático das rotas e tabelas.
- [x] Executar Grill Me obrigatório sobre prioridades de colunas antes de qualquer alteração dependente.
- [x] Registrar evidências locais já existentes e a limitação do ambiente atual, sem implementar escolha de prioridades sem resposta.
- [x] Aplicar o padrão mobile aprovado às tabelas horizontais priorizadas, preservando desktop e todos os dados.
- [x] Validar os fluxos em navegador, em 390px e desktop, e registrar screenshots locais da spec.

## Out of scope

- Redesign ou alteração das tabelas dependentes da prioridade do usuário.
- Dados reais e deploy.

## Grill Gate

Decision: needed

Reason: a regra especial exige escolha do usuário para prioridade, apresentação ou ocultação de colunas em cada página com tabela. O inventário e bugs independentes podem progredir antes dessa resposta.

Questions:

1. Confirmar as prioridades propostas por página e o padrão de apresentação mobile, sem decidir unilateralmente quais dados ficam fora do resumo.

Answers:

1. Em 2026-09-21, o usuário aprovou a proposta: cartões compactos em `<=480px`, sem eliminar informação; campos secundários ficam em detalhe expansível ou scroll explicitamente indicado. Ações ficam em menu, salvo ação principal recorrente. Valores monetários têm destaque e alinhamento à direita; status usa badge curto. As prioridades são: Lançamentos (título, vencimento, valor); Conciliação (data/descrição/título, valor, situação/pago); Faturas e Boletos (identificação, contraparte, vencimento, valor, status); Em aberto (título, contraparte, vencimento, saldo); Contas (conta, saldo, status); Categorias (categoria, natureza, status); Clientes (identificação, documento, cidade/UF); Produtos (descrição, venda, saldo); Movimentos (produto/documento, valor total, data); Faturas a receber (fatura/documento, cliente, vencimento, valor); Regras (identificação, próxima execução ou valor/parcelas); Compras (cartões por subtabela); Fluxo de caixa (período, fechamento, saldo inicial); Vendas (cliente, emissão, venda líquida); DRE/DRO e Comparativos (todos os três campos); Importações (data/hora, arquivo, status); modal de produto (descrição/código, venda, saldo).

## Progress

- 2026-09-21 - Iniciado inventário a partir das rotas, páginas, estilos e specs mobile anteriores.
- 2026-09-21 - Inventariadas 19 telas/componentes com tabelas. Em `max-width: 768px`, a base aplica rolagem horizontal e largura mínima de 640px ou 720px; em 390px, qualquer tabela sem `mobile-compact-table` exige rolagem lateral para acessar todas as colunas.
- 2026-09-21 - Confirmadas regras compactas em `max-width: 480px` para Conciliação, Faturas/Boletos principais, Movimentos, Produtos, Clientes, Faturas a receber, Contas, Categorias e itens financeiros em aberto.
- 2026-09-21 - Não havia `npm` nem `node_modules` no host; `pnpm audit` também não consegue auditar `package-lock.json`. Não foi possível iniciar Vite ou gerar evidência nova de navegador sem instalar dependências, o que não foi necessário para este levantamento read-only.
- 2026-09-21 - O destino global `G:\Meu Drive\.agentes` não está montado neste host. Nenhuma alteração visual foi feita nesta rodada; a cópia global não se aplica ainda.
- 2026-09-21 - Gerado o PDF de Grill Me `output/pdf/sal-002-duvidas-prioridades-mobile.pdf`, revisado por renderização de suas três páginas.
- 2026-09-21 - Usuário aprovou as prioridades e o padrão de apresentação propostos no Grill Me.
- 2026-09-21 - Iniciada a implementação após a autorização explícita do usuário. A primeira entrega cobre regras, fluxo de caixa, vendas, DRE/DRO, comparativos, histórico de importações e a busca global de produtos; Boletos e Compras seguem como próximos blocos pela maior densidade/interação.
- 2026-09-21 - Aplicado o padrão de cartões até 480px às tabelas de Regras, Fluxo de Caixa, Vendas, DRE/DRO, Comparativos, Histórico de Importações e Busca Global de Produtos. Em Boletos, foram cobertas as listas de atraso, pagamentos pendentes, excesso e boletos em aberto. Em Compras, foram cobertas projeções, custo por coleção/fornecedor, notas, parcelas, coleções e fornecedores.
- 2026-09-21 - Os campos continuam no DOM e no cartão com rótulos; a prioridade aprovada ocupa o cabeçalho do cartão, valores ficam à direita e ações continuam acessíveis. O histórico de importações ganhou badge compacto de status.
- 2026-09-21 - Validação no navegador local com SQLite descartável e dados fictícios: Histórico de Importações exibiu cinco cartões em 390×844, largura de tabela 294px e `documentWidth` 390px (sem overflow). Desktop 1440px também não apresentou overflow. Capturas das rotas de Boletos, Fluxo de Caixa e Vendas foram registradas, mas a demo não retornou linhas para os filtros padrão dessas telas.
- 2026-09-21 - O destino global `G:\Meu Drive\.agentes` não está montado neste macOS (`/Volumes/G/Meu Drive/.agentes` indisponível); os artifacts locais obrigatórios foram preservados.
- 2026-09-21 - Encerrados ao fim da validação o backend local em `127.0.0.1:8000`, o Vite em `127.0.0.1:5173` e a sessão temporária do navegador; nenhum processo de produção foi tocado.
- 2026-09-21 - Inspeção read-only da produção, com sessão do usuário já existente: a grade de planejamento por marca × coleção e a lista de boletos tinham linhas preenchidas. A navegação não executou ações, filtros, downloads, emissões, baixas, cancelamentos nem alterações de dados. Esses dados e imagens de produção não foram copiados para o repositório ou para artifacts.
- 2026-09-21 - Com base nessa referência visual, a grade variável por marca × coleção passou a cartões no mobile: marca no cabeçalho, uma coleção por campo rotulado e ações no rodapé. Também foram cobertas parcelas de nota, detalhe de marca por coleção, pedidos da coleção, marcas desativadas, fornecedores não classificados e o modal de clientes da cobrança.
- 2026-09-21 - Achado visual reproduzido por inspeção read-only em produção: em Safari, a tabela de Boletos em viewport CSS de 433px mantinha o `colgroup` desktop após as linhas virarem grid. Os cartões mediam 38px apesar de o container ter 322px, cortando rótulos e conteúdo. Nenhuma ação foi executada na produção.
- 2026-09-21 - Corrigido no desenvolvimento: o padrão `mobile-compact-table` passa a sair do algoritmo de layout de tabela no celular, oculta o `colgroup` desktop e força `tbody`, linhas e células a ocuparem 100% da largura. Em validação local na mesma largura, uma linha fictícia mediu 335px para uma tabela de 335px, sem overflow; rótulos, valor, status e ações ficaram visíveis.
- 2026-09-21 - Encerrados após a revalidação a sessão temporária do navegador, backend local (`127.0.0.1:8000`) e Vite (`127.0.0.1:5173`). As portas foram confirmadas sem listener; a produção não foi tocada.
- 2026-09-21 - Auditoria posterior ao achado Safari: o mesmo risco estrutural existia nas tabelas ativas de Faturas, Boletos e modal Clientes da Cobrança, Em aberto, busca global de produtos e modal marca × coleção de Compras. Há ainda ocorrências no componente legado `BoletosPage`, que não atende a rota ativa. Todas usam o mesmo padrão CSS agora corrigido; tabelas compactas sem `colgroup` não compartilham essa causa.
- 2026-09-21 - Revalidação com o seed oficial local: ele criou 3 contas, 10 lançamentos financeiros, 25 registros comerciais/Linx/boletos e 3 transações bancárias, todos fictícios. O seed trazia boletos Inter como `EM_ABERTO`, valor que o dashboard não reconhece como pendente; foi corrigido para `A receber`, mesmo status do importador, e os testes específicos passaram.
- 2026-09-21 - Revalidação preenchida: Boletos exibiu um registro do seed e Vendas exibiu quatro registros em 390×844 e 1440×1000, sem overflow do documento. No SQLite local, os endpoints de Fluxo de Caixa, resumo de relatórios, Marcas e planejamento de Compras retornaram 500; Compras também não é coberta pelo seed oficial. Para isolar o comportamento visual, foram usadas somente fixtures transitórias no DOM local, com nomes e valores explicitamente fictícios, para Fluxo, DRE, DRO e três tabelas de Compras. Nenhum dado de produção foi usado ou gravado.
- 2026-09-21 - Todas as linhas/cards revalidadas tiveram largura integral do respectivo wrapper em 390px (Boletos 292px, Vendas 264px, Fluxo 278px, DRE/DRO 262px e Compras 294px), sem overflow horizontal do documento. Desktop foi preservado para Boletos, Vendas, Fluxo, DRE e Compras.

## Decisions

- Decision: manter separado o levantamento novo da spec histórica de implementação mobile.
  Reason: SAL-002 é auditoria abrangente e inclui uma decisão pendente do usuário.
  ADR needed: no
- Decision: adotar cartão compacto até 480px, com detalhes expansíveis ou scroll explicitamente indicado para dados secundários.
  Reason: decisão expressa do usuário após Grill Me; preserva dados financeiros e reduz rolagem lateral no celular.
  ADR needed: no
- Decision: desligar explicitamente o `colgroup` de desktop quando uma tabela vira cartões no celular.
  Reason: Safari/WebKit continua usando as larguras das colunas no cálculo do grid, encolhendo os cartões e ocultando conteúdo.
  ADR needed: no

## Validation

Commands run:

- [x] Inventário estático de rotas, tabelas e CSS.
- [x] `pdfinfo output/pdf/sal-002-duvidas-prioridades-mobile.pdf` - PDF A4 com três páginas.
- [x] `pdftoppm -png -r 144 output/pdf/sal-002-duvidas-prioridades-mobile.pdf ...` - três páginas renderizadas e inspecionadas visualmente.
- [x] `cd frontend && pnpm run typecheck` — passou.
- [x] `cd frontend && pnpm run build` — passou.
- [x] Navegador local (`agent-browser`) — login com conta fictícia e navegação em 390×844 e 1440×1000.
- [x] `git diff --check` — passou.
- [x] `uv run --project backend python scripts/security_scan.py` — passou após as alterações.
- [x] `cd frontend && pnpm run typecheck` — passou novamente após completar as grades e modais remanescentes.
- [x] `cd frontend && pnpm run build` — passou novamente após completar as grades e modais remanescentes.
- [x] Navegador local (`agent-browser`) em 433×1260, mesma largura CSS observada na produção — sem overflow do documento; tabela e linha fictícia ficaram com 335px, e o cartão com duas colunas de 253px e 50px.
- [x] `env SALOMAO_ENV_FILE=.env.local PYTHONPATH=. uv run python scripts/seed_local_demo.py` — seed oficial local de dados fictícios recriado.
- [x] `PYTHONPATH=. uv run --extra dev pytest tests/test_local_demo_seed.py tests/test_boletos.py -q` — 19 passaram; nove avisos de depreciação já existentes.
- [x] `uv run ruff check app/services/local_demo_seed.py` — passou.
- [x] Navegador local (`agent-browser`) — Boletos e Vendas preenchidos em 390×844 e 1440×1000, sem overflow; fixtures locais identificadas para Fluxo, DRE/DRO e Compras quando o seed/endpoint local não forneceu a variante preenchida.

## Implementation evidence

| Rota / cenário | Viewport | Evidência | Resultado |
| --- | --- | --- | --- |
| `/sistema/importacoes-gerais`, cinco batches fictícios | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-importacoes-mobile-390x844.png` | cartões rotulados, badge de status e sem overflow horizontal |
| `/sistema/importacoes-gerais`, cinco batches fictícios | 1440×1000 | `artifacts/2026-09-21-mobile-interface-inventory/after-importacoes-desktop-1440x1000.png` | tabela desktop preservada e sem overflow do documento |
| `/financeiro/cobranca/boletos`, filtro padrão sem itens | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-boletos-mobile-390x844.png` | rota e controles renderizados; revalidação com registros de alertas fica pendente |
| `/financeiro/cobranca/boletos`, linha visual fictícia local | 433×1260 | `artifacts/2026-09-21-mobile-interface-inventory/after-boletos-mobile-433x1260-fixture-local.png` | cartão ocupa toda a tabela; seleção, cliente, vencimento, valor, status e ações visíveis; sem overflow |
| `/financeiro/cobranca/boletos`, registro do seed oficial local | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-boletos-populated-mobile-390x844.png` | cartão preenchido; sem corte ou overflow |
| `/financeiro/cobranca/boletos`, registro do seed oficial local | 1440×1000 | `artifacts/2026-09-21-mobile-interface-inventory/after-boletos-populated-desktop-1440x1000.png` | tabela desktop preservada; sem overflow |
| `/compras/planejamento`, estado local | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-planejamento-mobile-390x844.png` | três tabelas compactas no DOM e sem overflow; a base fictícia não contém marcas/compras |
| `/compras/planejamento`, estado local | 1440×1000 | `artifacts/2026-09-21-mobile-interface-inventory/after-planejamento-desktop-1440x1000.png` | desktop preservado e sem overflow do documento |
| `/compras/planejamento`, fixture transitória local | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-planejamento-mobile-390x844-fixture-local.png` | marca × coleção, coleção e fluxo preenchidos com valores fictícios; sem corte ou overflow |
| `/compras/planejamento`, fixture transitória local | 1440×1000 | `artifacts/2026-09-21-mobile-interface-inventory/after-planejamento-desktop-1440x1000-fixture-local.png` | desktop preservado |
| `/caixa-resultados/fluxo-caixa`, filtro padrão sem pontos | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-cashflow-mobile-390x844.png` | rota e alternância renderizadas; revalidação com projeções fica pendente |
| `/caixa-resultados/fluxo-caixa`, fixture transitória local | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-cashflow-mobile-390x844-fixture-local.png` | dois cartões com todos os campos e fechamento; sem overflow |
| `/caixa-resultados/fluxo-caixa`, fixture transitória local | 1440×1000 | `artifacts/2026-09-21-mobile-interface-inventory/after-cashflow-desktop-1440x1000-fixture-local.png` | desktop preservado |
| `/caixa-resultados/vendas`, filtro padrão sem itens | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-vendas-mobile-390x844.png` | rota renderizada sem overflow; revalidação com vendas fica pendente |
| `/caixa-resultados/vendas`, quatro registros do seed oficial local | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-vendas-populated-mobile-390x844.png` | quatro cartões preenchidos; sem corte ou overflow |
| `/caixa-resultados/vendas`, quatro registros do seed oficial local | 1440×1000 | `artifacts/2026-09-21-mobile-interface-inventory/after-vendas-populated-desktop-1440x1000.png` | tabela desktop preservada; sem overflow |
| `/caixa-resultados/dre`, fixture transitória local | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-dre-mobile-390x844-fixture-local.png` | contas, valor e percentual visíveis em cartões |
| `/caixa-resultados/dre`, fixture transitória local | 1440×1000 | `artifacts/2026-09-21-mobile-interface-inventory/after-dre-desktop-1440x1000-fixture-local.png` | tabela desktop preservada |
| `/caixa-resultados/dro`, fixture transitória local | 390×844 | `artifacts/2026-09-21-mobile-interface-inventory/after-dro-mobile-390x844-fixture-local.png` | contas, valor e percentual visíveis em cartões |

Os screenshots refletem ambiente local com conta e dados fictícios. Não há dados reais, credenciais ou arquivos operacionais nos artifacts.

## Next step

Não há pendência de implementação ou de evidência do comportamento responsivo de SAL-002. Como acompanhamento independente do escopo visual, o SQLite local retorna 500 para Fluxo de Caixa, resumo de relatórios, Marcas e planejamento de Compras, e o seed oficial não contém árvore configurada de DRE/DRO nem registros de Compras; as evidências desses casos são fixtures locais de layout, não validação funcional do backend. Nenhuma alteração em produção foi autorizada ou executada; a referência de produção usada nesta rodada foi somente leitura.

## Inventory

Viewport de risco: 390×844 (celular). Evidência estática: `frontend/src/styles/pages.css:5253-5320` e `:7388-7482`. Asterisco indica evidência visual histórica versionada.

| Rota / tela | Tabela e colunas relevantes | Comportamento atual em 390px | Problema / impacto | Evidência |
| --- | --- | --- | --- | --- |
| `/financeiro/lancamentos` | Lançamento, fluxo, conta, categoria, vencimento, status, valor, ações | Variante compacta | Referência positiva; sem achado estático novo | `2026-06-03.../05-lancamentos-padrao-bom-compacto.png` * |
| `/financeiro/conciliacao` | Extrato: data, extrato, valor, situação; Lançamentos: vencimento, lançamento, categoria, valor, pago | Cartões compactos | Revalidar dados/interações; valor já ficou fora antes | `01-conciliacao-valor-fora-da-tela.png`, `02-mobile-compact-reconciliation.png` * |
| `/financeiro/cobranca/faturas` | título, cliente, vencimento, valor, status, ações | Cartões compactos | Revalidar filtros e ações | `03-mobile-compact-billing.png` * |
| `/financeiro/cobranca/boletos` | cliente, documento, emissão, vencimento, valor, status, boleto/ações; atraso, pagas e excesso | Cartões compactos | Safari/WebKit encolhia cartões por herdar `colgroup` desktop; corrigido no desenvolvimento e revalidado com fixture local | `04-boletos-layout-quebrado.png`, `03-mobile-compact-billing.png`, `after-boletos-mobile-433x1260-fixture-local.png` * |
| `/financeiro/em-aberto` | título, cliente/fornecedor, vencimento, saldo | Cartões compactos | Revalidar ordenação/ações | `FinanceOpenItemsPage.tsx` |
| `/cadastros/contas` | conta, tipo, saldo inicial, OFX, saldo, Inter, status, ações | Cartões compactos | Saldo era parcial; prioridade final pendente | `06-contas-saldo-parcial.png`, `04-mobile-compact-cadastros.png` * |
| `/cadastros/categorias` | código, categoria, natureza, regra/DRE, status, ações | Cartões compactos | Revalidar controles | `MasterDataPage.tsx` |
| `/cadastros/clientes` | tipo, código, razão social, fantasia, documento, cidade/UF, boleto, modo, dia, juros, atualização | Cartões compactos | Tabela muito densa; prioridade pendente | `04-mobile-compact-cadastros.png` * |
| `/cadastros/produtos` | código, descrição, referência, custo, venda, saldo, fornecedor, coleção, status, atualização | Cartões compactos | Venda/saldo eram inacessíveis; confirmar campos secundários | `03-produtos-venda-saldo-fora-da-tela.png`, `04-mobile-compact-cadastros.png` * |
| `/cadastros/movimentos` | lançamento, tipo, documento, produto, coleção, quantidade, valor unitário/total, custo, natureza, data | Cartões compactos | Valores eram inacessíveis; confirmar campos secundários | `02-movimentos-valores-fora-da-tela.png`, `04-mobile-compact-cadastros.png` * |
| `/cadastros/faturas-a-receber` | fatura, cliente, emissão, vencimento, parcela, valor, documento, identificador | Cartões compactos | Identificação versus vencimento depende de prioridade | `CadastrosOpenReceivablesPage.tsx` |
| `/cadastros/regras` | recorrências: regra, tipo, frequência, próxima execução; empréstimos: contrato, credor, parcelas, valor | Scroll 640px | Agenda/valor não cabem integralmente | `CadastrosRulesPage.tsx` |
| `/compras/planejamento` | coleções, marcas, faturas, parcelas, fornecedores, pedidos e modal marca/coleção | Várias tabelas 640px/720px | Alta densidade; valores/parcelas exigem scroll | `PurchasePlanningPage.tsx` |
| `/caixa-resultados/fluxo-caixa` | período, saldo inicial, crediário, cartão, despesas, previsão de compras, fechamento | Scroll 640px | Fechamento fora da área inicial | `CashflowPage.tsx` |
| `/caixa-resultados/vendas` | nota, cliente, emissão, lançamento, itens, quantidade, venda bruta, devoluções, venda líquida | Scroll 640px | Resultado líquido exige scroll | `SalesReportPage.tsx` |
| `/caixa-resultados/dre` e `/dro` | contas, valor, percentual | Scroll 640px | Valor pode ficar fora da área inicial | `ReportsPage.tsx` |
| `/caixa-resultados/comparativos` | mês, atual, ano anterior | Scroll 720px | Valores comparativos exigem scroll | `ResultsComparativesPage.tsx` |
| `/sistema/importacoes-gerais` | data/hora, arquivo, tipo, processo, status, observação | Scroll 640px | Status/observação podem não ser acessíveis na área inicial | `SystemImportsGeneralPage.tsx` |
| modal global de produto | código, descrição, referência, marca, coleção, saldo, venda | Tabela horizontal | Saldo/venda relevantes para escolha; confirmar se entra no escopo | `GlobalProductSearchModal.tsx` |

## Findings independent of priority

- Tabelas não compactas mantêm largura mínima de 640px/720px até 768px. Em celulares de 390px não cortam o documento, mas exigem rolagem lateral e não têm afordância consistente.
- As abas têm máscara/gradiente em ≤480px; o comportamento de scroll das tabelas não compactas permanece inconsistente entre wrappers.
- Não foi encontrada por inspeção estática regra que faça conteúdo principal sair do viewport vertical. A validação dinâmica está pendente por falta do runtime frontend local.
