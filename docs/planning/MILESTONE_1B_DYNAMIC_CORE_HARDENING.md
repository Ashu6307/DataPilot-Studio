# Milestone 1B — Dynamic Data Core Hardening

Status: Complete — 2026-07-17. All named acceptance suites and release gates pass; one test-only dependency warning is documented in `docs/testing/DEPENDENCY_WARNINGS.md`.

Baseline: protected local tag `v0.1.0-m1a` at `39d4dba`.

## Objective

Harden the generic Phase 1 data core before advanced reconciliation, portal/PDF automation, licensing, team features, or AI. All behavior remains source-driven, canonical-ID based, reviewable, deterministic, and local-first.

## Work packages

1. Discovery: multi-level headers, merged-cell forward fill, separated table regions, repeated-header/footer classification, evidence, alternatives, and overrides.
2. Schema drift: explicit categories, policy modes, confidence thresholds, mapping suggestions/decisions/history, and impact preview.
3. Calculations: versioned typed expression trees; no `eval`, `exec`, SQL, JavaScript, shell, or dynamic imports.
4. Execution: persistent local jobs, structured progress, cooperative cancellation, checkpoints, restart recovery, and isolated partial artifacts.
5. Supportability: metadata/workflow migrations, bounded memory policy, structural golden workbooks, measured performance, and sanitised support bundles.
6. Demonstrations: five anonymised, structurally different profiles with workflow, expected output, acceptance tests, and walkthroughs.

## Exit criteria

- Existing M1A workflows load or receive an explicit tested migration.
- All discovery and mapping decisions are user-reviewable.
- Low-confidence/ambiguous mappings block unless an explicit policy and user decision permit continuation.
- Calculations type-check before execution and emit row/lineage/audit metrics.
- Cancelled, partial, and failed jobs never appear successful.
- Database upgrades back up first and fail without partial schema application.
- Support bundles omit raw rows and secret values by default.
- Golden workbook checks compare semantics, not ZIP bytes.
- Performance results identify hardware, data shape, date, limits, and sampled/full behavior.
- Full Python, frontend, E2E, build, and dependency-security gates pass.

## Explicit deferrals

Append/join/pivot, full reconciliation/comparison, portal automation, PDF/OCR, schedulers/triggers, unrestricted plugins, licensing enforcement, RBAC/team/cloud, and AI remain outside M1B.
