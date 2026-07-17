# ADR-015: Typed Workflow DAG Orchestration

## Status

Accepted — 2026-07-17.

## Decision

Introduce a strict `DagWorkflow` 3a.1 orchestration contract, closed capability
and adapter registries, static validation, deterministic planning, and a local
background executor. Orchestration delegates data semantics to existing engines.
Artifacts are materialized outside SQLite; only metadata and minimal evidence
are persisted.

## Consequences

Workflows become reusable, diffable, parameterized, and recoverable without
domain logic entering the graph engine. New node types require an explicit
versioned contract, adapter, entitlement capability ID, tests, and migration
assessment. Dynamic plugins and arbitrary code remain prohibited.
