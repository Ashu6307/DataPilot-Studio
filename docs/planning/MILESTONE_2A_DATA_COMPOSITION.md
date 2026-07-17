# Milestone 2A — Dynamic Data Composition Engine

Status: Implemented on 2026-07-17; release evidence is recorded in the acceptance matrix.

## Objective and boundary

Milestone 2A adds generic, metadata-driven composition for multiple CSV/XLSX/XLSM
sources. It introduces no customer, company, or industry rules. Fuzzy reconciliation,
browser/PDF/email automation, licensing, RBAC, AI, and remote connectors remain deferred.

## Delivered work packages

1. Read-only recursive folder scans and multi-upload catalogs with patterns, fingerprints, duplicate/incremental states, discovery profiles, and quarantine.
2. Versioned canonical schema alignment with per-source mappings, defaults/constants, safe casts, missing/extra policy, preview, and audited user decisions.
3. Heterogeneous append/union with stable source file, table, row, and source-ID lineage plus six duplicate-row policies.
4. Exact inner/left/right/full/semi/anti joins with key normalisation, null/duplicate policy, cardinality estimates, expansion protection, and unmatched outputs.
5. Typed grouped aggregation with nine functions, multiple measures, null policy, percentage, rank, running total, ordering, and Top N.
6. Pivot/unpivot with output-shape limits, fill/null policy, and memory-risk preview.
7. Conditional multi-field/date splitting to CSV, Excel files, workbook sheets, or deterministic ZIP packages with safe names and collision protection.
8. Evidence packages containing outputs, rejected files/rows, alignment, summaries, manifests, applied plans, audit logs, and SHA-256 fingerprints.
9. Composition API/background execution, SQLite migration v3, Composition Studio UI, fixtures, performance benchmark, and compatibility migration to workflow schema 1.2.

## Safety invariants

- Source bytes are copied into the isolated workspace and fingerprint-checked before and after execution.
- No fixed range, sheet, header, or column position is embedded in the composition engine.
- Many-to-many joins block until explicitly approved.
- Every non-eligible file and rejected/review row is represented in evidence.
- Output paths are resolved below the run directory; existing files are never overwritten.
- Cancelled/failed jobs cannot expose successful output state.
- Expression conditions use the closed typed expression engine; no dynamic evaluation is used.

## Compatibility and deferral

Workflow JSON 1.0 and 1.1 migrate deterministically to 1.2. M1A/M1B APIs and
runtime paths remain available. Advanced reconciliation, comparison, visual DAGs,
scheduling/watchers, remote delivery, and commercial/team features are later milestones.
