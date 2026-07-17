# Implementation Roadmap

## Milestone 0 — Product foundation (complete)

Documentation, monorepo, pinned dependencies, contracts, capability interfaces, SQLite repository protocols, isolated workspace, hashing, fixtures, quality gates, and a headless sample workflow. Exit: a versioned sample runs end to end with fingerprint and row reconciliation tests.

## Milestone 1A — Dynamic data core vertical slice (complete, protected baseline)

Project/source APIs, Excel/CSV discovery, overrideable header selection, column profile, canonical mapping, initial cleaning/validation registries, bounded preview, safe workbook pack, manifests, run history, workflow saving, and guided React UI. Exit: acceptance criteria in `MILESTONE_1_DYNAMIC_DATA_CORE.md` pass on reordered/renamed fixtures.

## Milestone 1B — Core hardening (complete, 2026-07-17)

Background execution/cancellation, stronger table-region and multi-row-header discovery, schema drift compare/repair, calculation/group operations, checkpoints, golden workbooks, measured 10k/100k/500k budgets, support bundles, workflow/database migrations, and five structurally distinct demonstration profiles are implemented. Tauri packaging remains a later commercialisation concern and was not claimed in this hardening milestone.

## Milestone 2A — Dynamic data composition (complete, 2026-07-17)

Multi-source/folder ingestion, versioned canonical alignment, append/union, exact
joins with cardinality gates, grouped aggregation, pivot/unpivot, dynamic split,
derived-only evidence packages, background execution, and Composition Studio UI.

## Milestone 2B — Reconciliation and comparison

Referential integrity, key-based dataset comparison, staged exact/tolerance/fuzzy
reconciliation, review queues, and report templates.

## Milestone 3 — Workflow platform

Typed visual DAG designer, runtime parameters, subflows, worker queue, scheduler/folder watcher, retries/checkpoints, and notifications.

## Milestone 4+ — Commercial/team/ecosystem

Installer/updater/signing/diagnostics/entitlements first; then identities, roles, sharing/private workers; finally isolated signed plugins, marketplace, governed AI, and enterprise connectors. Each begins only after the prior phase’s safety and compatibility gate.
