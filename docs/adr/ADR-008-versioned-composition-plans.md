# ADR-008 — Versioned composition plans

Status: Accepted, 2026-07-17.

Composition uses strict `2a.1` plans containing source IDs, discovery overrides,
canonical alignment, one closed-dispatch operation, and optional split policy.
SQLite stores configuration JSON by `(id, version)` and append-only per-source
alignment decisions. This keeps runtime behavior portable and auditable without
storing source rows.
