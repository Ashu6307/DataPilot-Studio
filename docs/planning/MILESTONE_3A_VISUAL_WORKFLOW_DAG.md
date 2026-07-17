# Milestone 3A — Typed Visual Workflow DAG

Milestone 3A promotes the completed data engines into a reusable, typed visual
workflow platform. The orchestration layer owns graph validation, planning,
versioning, parameters, control flow, checkpoints, and audit. It delegates data
work to the existing discovery, mapping, cleaning, validation, calculation,
composition, comparison, integrity, reconciliation, and export engines.

## Delivery order

1. `DagWorkflow` 3a.1 contracts and a closed capability registry.
2. Static validation, parameter resolution, deterministic planning, and diffs.
3. Workflow schema 1.4 and SQLite metadata schema 5 migrations.
4. Background runtime, materialized checkpoints, recovery, manual gates, and
   evidence regeneration.
5. React Flow canvas, palette, inspectors, problems, plan, run history, and five
   anonymised templates.
6. Acceptance, security, performance, and browser verification.

## Scope boundary

The milestone contains no scheduling/triggers, browser automation nodes,
PDF/OCR, email delivery, cloud collaboration, marketplace/plugin loading,
licensing enforcement, AI generation, or arbitrary code/SQL execution. Source
files remain immutable. SQLite stores metadata and minimal review evidence,
never complete source tables.

## Implementation map

- Contracts: `packages/contracts/workflow_dag.py`
- Orchestration: `packages/workflow_dag/`
- Persistence/API: `apps/api/app/dag_repository.py`, `main.py`, migration 5
- Canvas: `apps/web/src/WorkflowStudio.tsx`
- Templates: `samples/dag_templates/`
- Benchmarks: `scripts/benchmark_m3a.py`

The next compatibility versions are DAG schema `3a.1`, portable workflow schema
`1.4`, SQLite schema `5` for the DAG core, and ordered schema `6` for M2B result
artifact linkage used by evidence regeneration.
