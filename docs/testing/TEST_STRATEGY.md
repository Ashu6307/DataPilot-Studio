# Test Strategy

## Layers

- Unit: discovery scoring, profiling, mapping, every cleaning operation, every validator, fingerprinting, contract/secret validation, repositories, export formatting helpers.
- Property/invariant: input fingerprint stability, row reconciliation, deterministic rerun, idempotent cleaning where applicable, canonical mapping independent of column order.
- Integration: project/source/workflow/run API, SQLite transactions, CSV/XLSX pipelines, output workbook/manifest reopen.
- Frontend: state transitions, mapping/operation/rule forms, loading/empty/error/success states, accessible labels.
- End to end: create project → upload → discover/override → map → configure → preview → execute → inspect/download/history.
- Performance: opt-in synthetic 100k-row CSV baseline with bounded preview; record timing without a flaky hard threshold in CI.
- Security: path sanitisation, formula injection, secret configuration rejection, unsupported/corrupt files, no raw rows in metadata.

## Release gates

All critical tests, lint, typecheck, and production build must pass. Generated workbooks must reopen with expected sheets, filters, freeze panes, counts, fingerprint, workflow version, and run ID. A known critical/high security issue blocks milestone completion.

## Fixtures

`scripts/generate_fixtures.py` deterministically creates anonymised CSV/XLSX inputs for headers at row 1/after titles, reordered/renamed columns, blank leading/repeated headers, leading-zero IDs, mixed values, invalid dates, duplicates, missing required values, differing counts, empty/corrupt files, and a configurable large synthetic file.

