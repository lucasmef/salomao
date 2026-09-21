# Architecture Decision Records

This file stores durable decisions that are architectural, expensive, risky, or hard to reverse.

Do not record every small implementation detail here.

---

## ADR-001 - BuilderFlow adoption

Status: active
Date: 2026-06-03

### Context

The project uses AI-assisted development and needs a lightweight way to preserve context across sessions without creating heavy process overhead.

### Decision

Adopt BuilderFlow as the default AI-assisted development workflow.

BuilderFlow uses:

- one skill: `builderflow`
- one living spec per feature in `specs/`
- minimal fixed documentation
- Grill Gate as an internal decision step
- ADRs only for architectural or hard-to-reverse decisions

### Consequences

- Less documentation fragmentation.
- Easier task resumption.
- Lower cognitive load.
- More responsibility on the agent to classify work correctly.

### Risks

- A single living spec can become too long if the task is too broad.
- The agent may under-ask questions if Grill Gate is too permissive.

### Mitigations

- Keep one feature per spec.
- Ask up to 5 decision-oriented questions when ambiguity is material.
- Treat architectural changes as requiring ADR and confirmation.

---

## ADR-002 - Rodadas multi-intake com decomposição autônoma

Status: active
Date: 2026-09-21

### Context

Manutenções do Gestor Financeiro podem chegar em uma única rodada com vários IDs de intake, de domínios e riscos diferentes. A regra anterior de uma spec por tarefa não explicava como receber a rodada completa sem criar PRDs paralelos ou perder a rastreabilidade de cada ID.

### Decision

BuilderFlow continua sendo o único processo de planejamento e execução. O executor recebe a rodada completa, carrega o contexto real, executa Grill Gate e define autonomamente quantas living specs são necessárias. Os itens são agrupados ou separados por domínio, risco e dependências, recebem ordem técnica e são executados sequencialmente.

Cada ID preserva o elo `SAL-ID → living spec → alteração ou achado → validação → evidência`. Grill Me permanece reservado a decisões materiais não inferíveis; itens independentes seguem enquanto uma decisão está pendente. Evidências visuais ficam em `specs/artifacts/<spec-slug>/`, com cópia global `gestor-financeiro-*` quando o volume estiver disponível.

### Consequences

- A quantidade de specs deixa de ser fixa e segue o risco real da rodada.
- A living spec continua substituindo PRD, TASKS, STATUS, HANDOFF e NOTES.
- Relatórios de auditoria e mudanças visuais podem coexistir sem misturar validações ou evidências.

### Risks

- Decomposição excessiva pode fragmentar contexto; insuficiente pode misturar riscos distintos.
- Evidência global pode não estar disponível no host de execução.

### Alternatives considered

- Uma única spec obrigatória por rodada: rejeitada porque mistura domínios e riscos independentes.
- Criar um sistema paralelo de PRDs por ID: rejeitado porque duplica o papel das living specs.
