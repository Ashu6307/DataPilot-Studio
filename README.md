# DataPilot Studio

DataPilot Studio is a local-first, metadata-driven data automation workspace. Milestone 2A adds multi-file/folder catalogs, versioned canonical alignment, append/union, exact joins with cardinality gates, grouped aggregation, pivot/unpivot, dynamic split outputs, deterministic evidence packages, and a background-enabled Composition Studio.

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
```

## Runtime safety

Runtime uploads, projects, run folders, outputs, and SQLite metadata are created below `.datapilot/` by default and are ignored by Git. Inputs are copied into an isolated read-only-style source area, fingerprinted, and checked again after processing. Outputs receive unique timestamped names and are never written over source paths.

## Scope

Implemented work covers Milestones 0, 1A, 1B, and 2A. Fuzzy/staged reconciliation, dataset comparison, schedulers/triggers, cloud/team capabilities, licensing enforcement, third-party plugin loading, AI, and desktop packaging are intentionally deferred.
