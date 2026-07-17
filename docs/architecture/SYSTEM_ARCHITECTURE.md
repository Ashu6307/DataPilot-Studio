# System Architecture

Status: accepted foundation, 2026-07-17. Source: PRD sections 7, 27-30, 33-34, 42.

## Context and boundaries

DataPilot Studio begins as a local modular monolith. A React client calls a versioned FastAPI surface. The API coordinates project/workflow repositories and a Python engine; it does not process rows in route handlers. SQLite stores metadata only. Files and output evidence remain in isolated filesystem run directories. These boundaries allow the same API/engine to run behind a future Tauri shell or remote worker.

## Components

| Component | Responsibility | Must not do |
|---|---|---|
| Web | Guided configuration, preview, progress/results | Embed processing or secrets |
| API | Validate contracts, authorize local handles, orchestrate services | Accept arbitrary server paths from clients |
| Contracts | Versioned discovery, mapping, workflow, run, plugin models | Depend on UI or storage |
| Data engine | Connect, discover, map, clean, validate, export | Use customer labels or positional business access |
| Repositories | Project, workflow and run metadata behind protocols | Store source rows |
| Filesystem workspace | Immutable uploads, run snapshots, outputs/manifests | Overwrite source inputs |
| Capability registry | Describe built-in/plugin interfaces and entitlements | Load untrusted code in this milestone |

## Dependency rule

`apps/web → HTTP contracts → apps/api services → packages/contracts + packages/data_engine + packages/workflow_schema → storage/export adapters`. Plugin contracts depend only on shared contracts. Engine packages never import React or API routes.

## Initial deployment

Both processes bind to loopback during development. CORS is restricted to configured local origins. The runtime root defaults to `.datapilot/`. SQLite uses explicit transactions and run finalisation occurs only after outputs and manifest are verified readable.

## Evolution

Repository protocols support PostgreSQL later; artifact handles support object storage later; run status contracts include queued/cancelling states for a worker later; the frontend avoids browser-only file assumptions so Tauri can supply a local API.

