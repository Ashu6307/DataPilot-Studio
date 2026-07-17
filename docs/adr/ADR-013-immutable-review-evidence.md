# ADR-013 — Immutable review evidence

Status: Accepted, 2026-07-17.

Manual decisions are append-only SQLite events. Corrections supersede rather than
replace prior decisions. Review records retain bounded configured evidence, not
raw source datasets. Decision memory is separately audited, project scoped by
default, exportable, and soft-deactivated on deletion.
