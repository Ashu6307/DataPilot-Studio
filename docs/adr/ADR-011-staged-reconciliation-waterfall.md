# ADR-011 — Ordered reconciliation waterfall

Status: Accepted, 2026-07-17.

Reconciliation uses an immutable ordered list of typed stages. Accepted records
are removed from later stages by default; reuse requires explicit configuration.
Every candidate and match retains its stage and reason. This prevents accidental
double matching while keeping cross-domain workflows configuration-driven.
