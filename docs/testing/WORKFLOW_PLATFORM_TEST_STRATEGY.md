# Workflow Platform Test Strategy

The M3A suite is layered:

- Contract/unit tests cover registry identity, strict serialization, parameter
  coercion/redaction, cycle/port/cardinality/reachability findings, plan order,
  fingerprints, diffs, and recursive subflow rejection.
- Integration tests cover schema 1.3→1.4 and database 4→5 migrations,
  persistence, background lifecycle, materialized artifacts, parallel-ready
  nodes, manual pause/resume, immutable decisions, and restart recovery.
- Template tests load, validate, document, and plan all five anonymised examples.
- Performance tests exercise 25/100-node graphs, branching, expansion,
  persistence, state updates, recovery, and evidence regeneration.
- Vitest verifies existing application states. Playwright covers the complete
  visual template → validate → plan → save → publish journey plus all protected
  M1/M2 journeys.

Negative security fixtures include secret-like values, path traversal, invalid
versions, incompatible ports, candidate budgets inherited from M2B, and
formula-leading export cells. Tests never remove assertions or weaken typing to
obtain a green build.

Run:

```powershell
python -m pytest
python -m ruff check .
python -m mypy
npm run lint
npm run typecheck
npm run test
npm run build
npm --workspace apps/web run test:e2e
```
