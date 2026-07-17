# ADR-009 — Exact joins and cardinality gate

Status: Accepted, 2026-07-17.

Milestone 2A permits exact keys after allowlisted normalisation only. Key frequency
analysis runs before join execution. A many-to-many result requires explicit plan
approval and otherwise blocks. This prevents accidental row explosion while keeping
estimates, actual expansion, nulls, duplicates, and unmatched rows reviewable.
Fuzzy and staged reconciliation remain separate future capabilities.
