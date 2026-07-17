# Milestone 0: Product Foundation

Status: complete for the documented Phase 0 scope — 2026-07-17

## In scope

- Required product, architecture, ADR, planning, safety, and testing documentation.
- Pinned React/FastAPI/Polars monorepo and local run commands.
- Versioned Pydantic contracts for workflows, mappings, operations, rules, discovery, runs, plugins, and entitlements.
- Connector/processor/validator/exporter repository protocols and capability registry.
- SQLite metadata schema behind repository interfaces.
- Isolated workspace, source hashing, filename/path controls, secret scanning, reason/error contracts, and structured logs.
- Deterministic anonymised fixture generator and test harness.

## Exit criteria

1. Repository quality commands run locally and are documented.
2. The sample workflow is machine-validatable, readable, portable, diffable, and secret-free.
3. A headless CSV fixture executes through mapping, three cleaning operations, three validation rules, export, manifest, and run record.
4. Source SHA-256 is unchanged and row counts reconcile under automated tests.
5. Capability/plugin/entitlement contracts have tests but no vendor coupling or untrusted loading.
6. Traceability marks every PRD area implemented, partial, planned, or deferred.

## Not complete until

All Python and frontend lint/type/tests/build pass. Any gap is reported as a blocker or explicit deferral; documentation existence alone is insufficient.

## Completion evidence

- A versioned anonymised workflow executes through CSV ingestion, mapping, three cleaning operations, three validation rules, Excel export, manifest, and run record.
- Source fingerprint, formula-safe export, workbook reopen, row reconciliation, failure-state audit, repository, and plugin/entitlement contract tests pass.
- Final gates: 34 Pytest tests, 2 Vitest tests, 2 Playwright journeys, Ruff, strict mypy, ESLint, TypeScript, and Vite production build all pass.
- The only test warning is Starlette's upstream notice that its current `TestClient` httpx adapter is deprecated in favour of a future `httpx2` package; it does not affect runtime API code.
