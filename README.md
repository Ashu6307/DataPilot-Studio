# DataPilot Studio

DataPilot Studio is a local-first, metadata-driven data automation workspace. Milestone 2B adds arbitrary key-based dataset and structure comparison, composite referential integrity, audited key normalisation, staged exact/tolerance/fuzzy/weighted reconciliation, governed manual review, decision memory, and deterministic evidence packages through a background-enabled Reconciliation Studio.

The source of truth is `docs/product/DataPilot_Studio_Commercial_PRD_v1.0.pdf`. Milestone scope and requirement status are recorded in `docs/planning/PRD_TRACEABILITY_MATRIX.md`.

## Prerequisites

- Python 3.12+ (tested with 3.14)
- Node.js 20.19+ (tested with 24)
- npm 11+

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
npm install
python scripts/generate_fixtures.py
python scripts/generate_composition_fixtures.py
```

Start the API and web app in separate terminals:

```powershell
python -m uvicorn apps.api.app.main:app --reload
npm run dev
```

Open `http://localhost:5173`. API docs are at `http://127.0.0.1:8000/docs`.

## Quality gates

```powershell
python -m ruff check .
python -m mypy
python -m pytest
npm run lint
npm run typecheck
npm run test
npm run build
npm --workspace apps/web run test:e2e
npm audit --audit-level=high
```

Fixture and reproducibility commands:

```powershell
python scripts/generate_fixtures.py
python scripts/generate_demo_profiles.py
python scripts/generate_golden_workbook.py
python scripts/benchmark_m1b.py
python scripts/benchmark_export.py
python scripts/benchmark_m2a.py
python scripts/benchmark_m2b.py
```

## Reconciliation Studio

Open the **Reconcile** workspace after starting the API and web app. Import two
canonical CSV/Excel datasets, choose business keys and comparison fields, preview
normalisation, order matching stages, inspect candidate budgets, and submit the
full background run. Successful runs expose Excel, CSV, JSON, and deterministic
ZIP evidence. Ambiguous candidates remain pending until an append-only review
decision is recorded.

## Runtime safety

Runtime uploads, projects, run folders, outputs, and SQLite metadata are created below `.datapilot/` by default and are ignored by Git. Inputs are copied into an isolated read-only-style source area, fingerprinted, and checked again after processing. Outputs receive unique timestamped names and are never written over source paths.

## Scope

Implemented work covers Milestones 0, 1A, 1B, 2A, and 2B. Schedulers/triggers, cloud/team capabilities, licensing enforcement, third-party plugin loading, AI, and desktop packaging are intentionally deferred.
