---
name: builderflow
description: Use BuilderFlow for lightweight context-driven AI-assisted development workflows. Trigger when the user says BuilderFlow or asks to implement, fix, refactor, investigate, research, or change architecture while preserving context, minimizing questions, and maintaining a single living spec per feature.
---

# BuilderFlow

BuilderFlow is a lightweight context-driven development workflow for solo builders and small teams.

The goal is to preserve context, reduce cognitive load, avoid unnecessary questions, and allow safe asynchronous work.

## Core principles

1. Work one feature or task at a time.
2. Read context before asking questions.
3. Ask only what cannot be inferred from docs or code.
4. Prefer small, reversible, verifiable changes.
5. Maintain one living spec per feature.
6. Register ADRs only for decisions that are architectural, expensive, risky, or hard to reverse.
7. Do not create separate PRD, TASKS, STATUS, HANDOFF, or NOTES files by default.
8. The living spec is the source of truth for planning, progress, status, handoff, validation, and next steps.

---

## Required context loading

Before planning or implementing, read if available:

1. `AGENTS.md`
2. `docs/CONTEXT.md`
3. `docs/ADR.md`
4. Recent or related files in `specs/`
5. Relevant code paths for the requested task
6. Similar implementations already present in the repository
7. Project-specific domain skills, if the repository defines them

Do not ask questions before checking these sources.

---

## Task classification

Classify every request using two fields:

```txt
Mode: build | bugfix | refactor | research | architecture
Complexity: low | medium | high | architectural
```

### Mode rules

Use `build` when the user asks for a new feature, screen, endpoint, component, integration, or behavior.

Use `bugfix` when the user reports an error, broken behavior, incorrect calculation, failed build, failed test, or regression.

Use `refactor` when the user asks to reorganize code without changing external behavior.

Use `research` when the task is investigative and should not change production code yet.

Use `architecture` when the task changes infrastructure, database, authentication, deployment, branching workflow, data model, core domain rules, or other hard-to-reverse decisions.

### Complexity rules

Use `low` when the task is local, objective, low risk, and easy to validate.

Use `medium` when the task touches multiple files or requires moderate product understanding.

Use `high` when the task touches important flows, financial logic, auth, imports, deployment, data consistency, security, privacy, or several modules.

Use `architectural` when the task changes a hard-to-reverse decision, system boundary, stack, database, deploy workflow, branch workflow, auth model, data model, or critical domain behavior.

---

## Grill Gate

BuilderFlow contains an internal Grill Gate.

The agent does not ask questions by default.

Before asking, infer from:

1. Documentation
2. ADRs
3. Existing code
4. Similar features
5. Naming conventions
6. Existing UI, API, data, and test patterns
7. Project-specific domain skills or rules

Ask questions only when at least one condition is true:

- Business rule is ambiguous.
- Acceptance criteria are missing and cannot be inferred.
- The scope is too broad.
- There are multiple valid implementation paths with different consequences.
- The change is architectural.
- The change may affect production data, auth, billing, financial logic, deploy, imports, privacy, or security.
- The user request conflicts with existing ADRs or project context.

If questions are needed:

- Ask at most 5 questions.
- Use numbered questions.
- Make each question short and decision-oriented.
- Do not ask questions already answered by code or docs.
- Do not implement architectural changes before confirmation.

If questions are not needed:

- Create or update the living spec.
- Proceed with implementation.

---

## Living spec

For each feature or task, create one markdown file:

```txt
specs/YYYY-MM-DD-short-slug.md
```

Examples:

```txt
specs/2026-05-22-import-orders.md
specs/2026-05-22-fix-dashboard-build.md
specs/2026-05-22-simplify-dev-prod-workflow.md
```

If an active spec for the same task already exists, update it instead of creating a duplicate.

The living spec replaces PRD, status, tasks, notes, and handoff.

Use this template:

```md
# [Feature or Task Name]

## Metadata

- Status: planned | waiting_user | in_progress | blocked | review | done
- Mode: build | bugfix | refactor | research | architecture
- Complexity: low | medium | high | architectural
- Created: YYYY-MM-DD
- Updated: YYYY-MM-DD

## Objective

Describe the intended outcome in 2 to 5 lines.

## Context

Summarize relevant product, technical, and repository context discovered before implementation.

## Scope

- [ ] Item included in this task
- [ ] Item included in this task

## Out of scope

- Item intentionally excluded
- Item intentionally excluded

## Grill Gate

Decision: not_needed | needed | completed

Reason:
Explain why questions were or were not necessary.

Questions, if any:
1. ...
2. ...

Answers:
1. ...
2. ...

## Acceptance criteria

- [ ] Observable criterion
- [ ] Observable criterion
- [ ] Validation criterion

## Implementation plan

- [ ] Step 1
- [ ] Step 2
- [ ] Step 3

## Progress

Use timestamped or ordered entries.

- YYYY-MM-DD HH:mm - Started context review.
- YYYY-MM-DD HH:mm - Found related implementation in `path/to/file`.

## Decisions

Record local decisions for this task.

- Decision: ...
  Reason: ...
  ADR needed: yes | no

## Files changed

- `path/to/file` - reason

## Validation

Commands run:

- [ ] `npm run lint`
- [ ] `npm run typecheck`
- [ ] `npm run test`
- [ ] `npm run build`

Results:

- ...

Frontend evidence:

- Required when the task changes user-facing frontend behavior or layout.
- Store screenshots in `specs/artifacts/YYYY-MM-DD-short-slug/`.
- Reference each screenshot path and the validated screen or flow.

## Risks

- Risk: ...
  Mitigation: ...

## Next step

State exactly what should happen next.

Examples:

- Await user answer to Grill Gate questions.
- Continue implementation from Step 2.
- Review diff locally.
- Merge after validation.
- Deploy after review.
```

---

## ADR rules

Use `docs/ADR.md` for durable architectural decisions only.

Do not create an ADR for every small decision.

Create or update an ADR when the task involves:

- Database choice
- Local versus production environment strategy
- Branching strategy
- Deploy strategy
- Authentication model
- Authorization model
- Payment or financial rules
- Import or synchronization architecture
- Framework or library replacement
- Data model change that is hard to reverse
- Security-sensitive behavior
- Privacy-sensitive behavior

ADR entry format:

```md
## ADR-XXX - Title

Status: proposed | active | superseded
Date: YYYY-MM-DD

### Context

...

### Decision

...

### Consequences

...

### Risks

...

### Alternatives considered

...
```

If a decision is architectural, do not implement it immediately unless the user explicitly confirmed it.

---

## Execution rules by mode

### build

1. Create or update the living spec.
2. Use Grill Gate if requirements are ambiguous.
3. Implement the smallest useful vertical slice.
4. Update the living spec before ending.
5. Validate with relevant commands.

### bugfix

1. Reproduce or locate the failure first.
2. Document the suspected cause in the living spec.
3. Make the smallest fix.
4. Validate the fix.
5. Document the result.

Do not rewrite unrelated code during a bugfix.

### refactor

1. Define behavior that must remain unchanged.
2. Prefer small, mechanical changes.
3. Avoid mixing refactor with new feature work.
4. Validate after each meaningful change.
5. Document files changed and risks.

### research

1. Do not change production code unless explicitly asked.
2. Investigate the codebase and relevant docs.
3. Produce findings in the living spec.
4. List options, tradeoffs, and recommendation.
5. If the recommendation is architectural, propose an ADR.

### architecture

1. Create a living spec with `Mode: architecture` and `Complexity: architectural`.
2. Run Grill Gate.
3. Propose alternatives.
4. Create or update ADR as `Status: proposed`.
5. Wait for user confirmation unless the user explicitly authorized implementation.
6. After confirmation, implement in small reversible steps.

---

## Validation rules

Detect the package manager and available scripts before running commands.

Prefer existing scripts from `package.json` or equivalent project files.

Common checks:

```txt
npm run lint
npm run typecheck
npm run test
npm run build
```

If using pnpm:

```txt
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

If using yarn:

```txt
yarn lint
yarn typecheck
yarn test
yarn build
```

If using a non-JavaScript stack, discover and use the repository's existing validation commands.

If a command does not exist, do not invent it. Record that it was unavailable.

Always update the living spec with:

- commands run
- result
- errors
- skipped validations and reason
- frontend manual test evidence when the task changes user-facing frontend behavior or layout

### Frontend-impact validation

When a task changes user-facing frontend behavior, layout, navigation, styling, forms, interactive states, or any visible screen:

1. Run the local web app temporarily after implementation.
2. Before starting, check whether the intended port is already in use.
3. Reuse an existing suitable local server when available, or start a temporary server on an available port.
4. Record the server command, port, PID/process, and shutdown result in the living spec.
5. Manually exercise the affected screens or flows in the browser.
6. Capture screenshots of every changed screen or materially affected state.
7. Save screenshots under `specs/artifacts/YYYY-MM-DD-short-slug/`.
8. Name screenshots with ordered, descriptive names such as `01-inbox-empty-state.png` or `02-editor-saving-state.png`.
9. Reference the screenshot paths in the living spec under Validation.
10. Stop every server, watcher, and child process started by the agent before the final response.

Do not mark a frontend-impacting task as done until the local server run, manual browser check, screenshots, spec update, and server shutdown are complete.

If the server cannot be started, the browser cannot be tested, or screenshots cannot be captured, mark the spec as `blocked` or `review`, explain the reason, and do not claim the frontend validation passed.

### Two-location proof copy

This rule applies to any agent (Claude, Codex, Gemini, Antigravity).

When a fix has visual impact and must be proven, save the screenshot in two places:

1. In the project: `specs/artifacts/<spec-slug>/` (the ordered names above).
2. In the global proofs folder: `G:\Meu Drive\.agentes` (in its root; create it if it does not exist).

Naming convention for the global copy: `<project>-<screen|area>-<YYYY-MM-DD>[-n].png`
(e.g. `gestor-financeiro-today-2026-05-29.png`). The name must make clear which
project / screen / fix the screenshot proves.

For this repository:

- Global proofs folder: `G:\Meu Drive\.agentes`
- Project slug (filename prefix): `gestor-financeiro`

Pure logic, infra, test, or build changes do NOT require manual testing or screenshots.

---

## Git and deploy policy

Before changing branches, environments, deployment scripts, release process, or infrastructure, discover the repository's current workflow from docs, code, CI config, and hosting/deploy files.

Rules:

- Do not assume a specific branch strategy such as `dev`/`main`.
- Do not assume a permanent dev environment on the server.
- Do not change deploy workflow without treating it as `Mode: architecture`.
- Branching, server, CI/CD, release, and deploy changes require ADR consideration.

If asked to implement a workflow, branching, server, or deploy change, classify as:

```txt
Mode: architecture
Complexity: architectural
Grill Gate: needed
ADR: required
```

---

## Final response format

At the end of a BuilderFlow task, respond with:

```md
## BuilderFlow summary

Mode: ...
Complexity: ...
Spec: `specs/YYYY-MM-DD-short-slug.md`
Status: ...

## Done

- ...

## Changed files

- `path/to/file` - reason

## Validation

- `command` - passed | failed | skipped
- frontend manual check - passed | failed | skipped
- screenshots - `specs/artifacts/YYYY-MM-DD-short-slug/...`

## Risks

- ...

## Next step

...
```

If blocked by questions, respond with:

```md
## BuilderFlow needs input

I reviewed the docs and code. These decisions are not inferable:

1. ...
2. ...

Spec created or updated:
`specs/YYYY-MM-DD-short-slug.md`
```

---

## Do not rules

Do not:

- create multiple process skills for the same workflow
- create separate PRD, TASKS, STATUS, HANDOFF, or NOTES files by default
- ask questions before reading docs and code
- ask more than 5 questions in Grill Gate
- implement architectural changes without confirmation
- overwrite existing docs without preserving content
- mix unrelated features in one spec
- make broad rewrites when a narrow change solves the task
- invent validation commands
- mark work as done without updating the living spec
