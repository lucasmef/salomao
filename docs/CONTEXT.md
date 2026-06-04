# Project Context

This file stores durable project context for Codex and BuilderFlow.

Update this file with stable facts about the product, stack, workflows, commands, conventions, and sensitive areas.

## Product

Describe the product here.

## User workflow

Describe how the user or team prefers to work.

Suggested default:

- one task at a time
- local development first
- AI agent executes asynchronously
- user reviews later
- deploy only after validation

## Agent workflow roles

- `builderflow` is the primary process skill. It governs task classification, Grill Gate, living specs in `specs/`, ADR handling, validation reporting, and final summaries.
- Project-specific skills, if present, are companion domain-rules skills. Use them for project-specific rules around data, sensitive modules, architecture, security, integrations, and repository conventions.
- Do not treat domain-rules skills as competing planning workflows.
- Frontend-impacting BuilderFlow tasks require temporary local server validation, browser testing, screenshots, and server shutdown before the task can be marked done.

## Development workflow

Document the branch, environment, review, and deploy model here.

Example:

```txt
dev: local development + Git
main: production branch + production server
```

## Stack

Document the actual stack after inspecting the repository.

## Commands

Document discovered commands here:

- install:
- dev:
- lint:
- typecheck:
- test:
- build:

## Frontend validation evidence

When a task changes user-facing frontend behavior, layout, navigation, styling, forms, interactive states, or any visible screen:

- run the local web app temporarily after implementation
- check for an existing server or occupied port before starting a new one
- record server command, port, PID/process, and shutdown result in the living spec
- manually test the affected screen or flow in the browser
- save screenshots under `specs/artifacts/<spec-slug>/`
- use ordered descriptive screenshot names, such as `01-today-list.png` or `02-editor-empty-state.png`
- reference screenshot paths in the living spec validation section
- stop every server, watcher, and child process started by the agent before final response

## Important conventions

Document project-specific conventions here.

## Sensitive areas

Document modules that require extra care, such as:

- authentication and authorization
- financial calculations
- imports and sync jobs
- production deploy
- database migrations
- customer, personal, or business data
