# DataPilot Studio engineering instructions

These instructions apply to the entire repository.

## Product boundaries

- Read `docs/product/DataPilot_Studio_Commercial_PRD_v1.0.pdf`, the traceability matrix, and relevant ADRs before material changes.
- Reference a PRD requirement, accepted issue, or milestone criterion for implementation work.
- Keep customer/process terminology in versioned workflows, mappings, rules, and templates—not in the generic engine.
- Never hard-code row ranges, column ranges, column positions, sheet names, filenames, or customer field labels in core processing.
- Do not implement deferred modules while a current milestone exit criterion remains unmet.

## Data safety

- Never modify, move, rename, or delete source inputs. Fingerprint every source before and after execution.
- Write every run to a unique isolated directory and reconcile rows read, written, rejected, and filtered.
- Preserve identifier text and leading zeros. Flag ambiguous dates and mixed types; do not silently coerce them.
- Never silently discard invalid rows. Findings require stable reason codes and readable messages.
- Never store source rows in SQLite. Never commit real company data or secrets.
- Workflow files contain credential references only. Normal logs and support data contain no raw sensitive rows.
- Do not run destructive SQL automatically. Propose it under `docs/sql/` and obtain approval first.

## Architecture and quality

- Keep business processing out of React components and API route handlers.
- Version every public configuration and operation contract. Downstream operations use canonical field IDs.
- Every operation reports metrics, warnings/errors, and audit metadata and supports bounded preview.
- Add anonymised fixtures and tests for supported edge cases.
- Run `python -m ruff check .`, `python -m mypy`, `python -m pytest`, `npm run lint`, `npm run typecheck`, `npm run test`, and `npm run build` after meaningful changes.
- Do not claim completion when checks fail. Document deliberate deferrals in the traceability matrix.

