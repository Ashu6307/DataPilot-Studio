# Milestone 1B Acceptance Matrix

Evidence status is changed to **Implemented** only with a named automated test.

| Package | Acceptance | Evidence | Status |
|---|---|---|---|
| Discovery | 2/3-row and merged headers flatten deterministically with configurable separator and duplicate disambiguation | `tests/unit/test_discovery_hardening.py` | Implemented |
| Discovery | Blank-row/column, repeated-header, and rectangular regions produce selectable table candidates with bounds/evidence | `tests/unit/test_discovery_hardening.py` | Implemented |
| Discovery | Totals, subtotals, notes, generated footers, and signature areas are classified but never silently removed | `tests/unit/test_discovery_hardening.py` | Implemented |
| Drift | Reorder, rename, add/remove, type/nullability, duplicate, values, level, sheet, table, and ambiguity are classified | `tests/unit/test_schema_drift.py` | Implemented |
| Mapping | Suggestions carry method/evidence/confidence; ambiguous or low-confidence suggestions require a user decision | `tests/unit/test_schema_drift.py`, `apps/web/e2e/workspace.spec.ts` | Implemented |
| Expressions | Every listed arithmetic/text/conditional/date operation type-checks and executes without arbitrary-code access | `tests/unit/test_expressions.py` | Implemented |
| Expressions | Zero division, null policy, error policy, invalid references, previews, row metrics, and lineage are explicit | `tests/unit/test_expressions.py` | Implemented |
| Jobs | Persistent lifecycle, progress, cancellation, retry eligibility, checkpoints, and restart recovery preserve terminal truth | `tests/integration/test_background_jobs.py` | Implemented |
| Migrations | Current SQLite and workflow `1.0` upgrade with backup/report; failures roll back; future majors block | `tests/integration/test_migrations.py` | Implemented |
| Support | Previewed bundle contains versions/sanitised diagnostics and excludes raw rows/secrets | `tests/unit/test_support_bundle.py` | Implemented |
| Golden | Workbook structure, formats, filters, panes, reason/audit fields, formulas, and reconciliation compare semantically | `tests/unit/test_golden_workbook.py` | Implemented |
| Performance | 10k/100k/500k and wide/high-cardinality budgets and measured local results are documented without invention | `tests/performance/test_m1b_budgets.py` | Implemented |
| Profiles | Five anonymised profiles contain workflow, fixture, expected output, docs, and acceptance coverage | `tests/integration/test_demo_profiles.py` | Implemented |
| UI | Drift review, nested calculation builder, and run monitor/cancel have component and E2E coverage | `apps/web/src/App.test.tsx`, `apps/web/e2e/workspace.spec.ts` | Implemented |
