# ADR-010 — Derived-only deterministic output packages

Status: Accepted, 2026-07-17.

Batch packages contain derived outputs and evidence selected by the runtime; source
files and credentials are excluded. Paths are sanitised and confined to isolated run
directories, existing files are never overwritten, and every artifact is hashed.
ZIP entries use stable sorting and timestamps so identical selected content produces
a deterministic archive structure.
