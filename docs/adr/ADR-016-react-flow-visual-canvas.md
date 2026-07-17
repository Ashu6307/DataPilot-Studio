# ADR-016: React Flow for the Visual DAG Canvas

## Status

Accepted — 2026-07-17.

## Decision

Use `@xyflow/react` for canvas navigation, selection, typed handles, connection
events, minimap, controls, and background grid. DataPilot owns node contracts,
validation, persistence, configuration panels, accessibility labels, and all
execution semantics.

## Consequences

The UI avoids a bespoke pan/zoom/selection engine while retaining a strict
backend source of truth. The dependency is pinned through `package-lock.json`
and covered by lint, strict TypeScript, production build, unit tests, audit, and
Playwright. React Flow is not a runtime or code-execution dependency.
