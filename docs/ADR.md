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
