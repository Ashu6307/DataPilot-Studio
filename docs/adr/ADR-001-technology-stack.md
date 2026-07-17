# ADR-001: Initial technology stack

Status: Accepted — 2026-07-17

## Decision

Use React 19.2.7, TypeScript 6.0.3, Vite 8.1.3, Tailwind CSS 4.3.3 and accessible native/headless patterns for the web; FastAPI 0.139.0 with Pydantic 2.13.4 for the API; Polars 1.42.1 as primary table engine; OpenPyXL 3.1.5 for workbook inspection; XlsxWriter 3.2.9 for output; DuckDB 1.5.4 as an available query adapter; SQLite for metadata. Exact dependencies are pinned. Node >=20.19 and Python >=3.12 are supported baselines.

## Rationale

This matches PRD section 27 while retaining a lightweight local deployment and future Tauri compatibility. Polars handles columnar transformation; OpenPyXL exposes sheet state/cells; XlsxWriter provides controlled professional exports. DuckDB is not added to every code path merely because it is available. TypeScript 6.0.3 is intentionally selected instead of 7.0.2 because the current `typescript-eslint` 8.64.0 peer contract supports TypeScript versions below 6.1; peer validation is not bypassed.

## Consequences

Two local processes are required initially. Excel fidelity is limited to supported tabular ingestion; macros/formulas are not executed. A future desktop ADR must decide the shell and Python service lifecycle.
