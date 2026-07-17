# Implementation Roadmap

## Milestone 0 — Product foundation (current)

Documentation, monorepo, pinned dependencies, contracts, capability interfaces, SQLite repository protocols, isolated workspace, hashing, fixtures, quality gates, and a headless sample workflow. Exit: a versioned sample runs end to end with fingerprint and row reconciliation tests.

## Milestone 1A — Dynamic data core vertical slice (current, limited)

Project/source APIs, Excel/CSV discovery, overrideable header selection, column profile, canonical mapping, initial cleaning/validation registries, bounded preview, safe workbook pack, manifests, run history, workflow saving, and guided React UI. Exit: acceptance criteria in `MILESTONE_1_DYNAMIC_DATA_CORE.md` pass on reordered/renamed fixtures.

## Milestone 1B — Core hardening (next recommended)

Background execution/cancellation, stronger table-region and multi-row-header discovery, schema drift compare/repair, calculation/group operations, checkpoints, golden workbooks, 100k-row budget, support bundle, workflow migrations, Tauri lifecycle experiment, and five structurally distinct demonstration profiles.

## Milestone 2 — Advanced operations

Append/join/pivot, referential integrity, dataset comparison, staged reconciliation, review queues, and report templates.

## Milestone 3 — Workflow platform

Typed visual DAG designer, runtime parameters, subflows, worker queue, scheduler/folder watcher, retries/checkpoints, and notifications.

## Milestone 4+ — Commercial/team/ecosystem

Installer/updater/signing/diagnostics/entitlements first; then identities, roles, sharing/private workers; finally isolated signed plugins, marketplace, governed AI, and enterprise connectors. Each begins only after the prior phase’s safety and compatibility gate.

