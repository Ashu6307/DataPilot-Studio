# ADR-012 — Governed fuzzy candidates

Status: Accepted, 2026-07-17.

Fuzzy and weighted stages require blocking constraints. Candidate estimates,
memory estimates, thresholds, maximum pairs, cancellation checks, tie detection,
and manual-review routing are mandatory. Unrestricted all-to-all fuzzy execution
is rejected rather than treated as a performance optimization opportunity.
