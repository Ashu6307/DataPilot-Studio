# ADR-014 — Reconciliation schema versions

Status: Accepted, 2026-07-17.

Reconciliation contracts use semantic compatibility marker `2b.1`; general
workflow envelopes advance from `1.2` to `1.3`; SQLite metadata advances to
schema version 4. The workflow migration is pure and tested. Database migration
uses the established backup, transaction, rollback, and failure-reporting path.
