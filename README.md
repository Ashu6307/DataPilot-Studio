# DataPilot Studio

DataPilot Studio is a local-first, metadata-driven data automation workspace. Milestone 3A adds a versioned typed workflow DAG, closed capability registry, visual canvas, static validation, deterministic planning, runtime parameters, conditional routing, reusable subflows, background node execution, manual checkpoints, workflow diffs, and review-aware evidence regeneration while preserving the completed M1/M2 engines.

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
python scripts/generate_dag_templates.py
python -m scripts.benchmark_m3a
```

## Reconciliation Studio

Open the **Reconcile** workspace after starting the API and web app. Import two
canonical CSV/Excel datasets, choose business keys and comparison fields, preview
normalisation, order matching stages, inspect candidate budgets, and submit the
full background run. Successful runs expose Excel, CSV, JSON, and deterministic
ZIP evidence. Ambiguous candidates remain pending until an append-only review
decision is recorded.

## Visual Workflow Studio

Create a project and open **Visual workflow studio**. Use the searchable palette
or one of five anonymised templates, connect typed ports, configure nodes,
validate the graph, inspect its deterministic execution plan, save/publish a
version, and submit the full run to background execution. The problems, plan,
and runs panels expose reason codes, parallel groups, checkpoints, progress,
cancel state, and recovery state. Published versions are immutable; edits create
reviewable new versions through the DAG API.

## Runtime safety

Runtime uploads, projects, run folders, outputs, and SQLite metadata are created below `.datapilot/` by default and are ignored by Git. Inputs are copied into an isolated read-only-style source area, fingerprinted, and checked again after processing. Outputs receive unique timestamped names and are never written over source paths.

## Scope

Implemented work covers Milestones 0, 1A, 1B, 2A, 2B, and 3A. Schedulers/triggers, cloud/team capabilities, licensing enforcement, third-party plugin loading, AI, and desktop packaging are intentionally deferred.
