# Milestone 2B — Dynamic Comparison and Reconciliation

Status: implemented and release-gated on 2026-07-17.

## Outcome

Milestone 2B adds configuration-driven comparison, structure drift review,
referential integrity, deterministic normalisation, ordered reconciliation,
governed fuzzy and weighted candidates, immutable manual review, optional
decision memory, and derived evidence packages. Core code contains no business
domain names, fixed keys, fixed rows, fixed columns, or fixed sheet names.

## Implementation sequence

1. Add strict `2b.1` contracts and workflow schema `1.3` migration.
2. Implement normalisation, Decimal-safe tolerance, comparison, and integrity.
3. Implement an ordered candidate waterfall with blocking and consumption rules.
4. Persist runs, review events, decision memory, and manifests in SQLite v4.
5. Integrate with the existing job, checkpoint, recovery, and isolated workspace.
6. Add professional Excel/CSV/JSON/deterministic-ZIP evidence.
7. Add Reconciliation Studio, anonymised profiles, tests, and measured budgets.

## Runtime flow

`source fingerprints -> optional comparison/integrity -> candidate estimate ->
ordered stages -> review routing -> isolated evidence -> manifest -> publish`

Only a successful terminal run publishes an output manifest. Cancellation and
failure retain no successful-output flag. Source fingerprints are checked before
and after execution.

## Scope boundary

This milestone does not add browser automation, PDF/OCR, email, licensing,
RBAC, cloud collaboration, AI generation, autonomous learning, arbitrary code,
or arbitrary SQL. Decision memory is explicit user-managed metadata and never
overrides blocking or review policies.

## Demonstration profiles

- `old_new_report_comparison`
- `vendor_invoice_reconciliation`
- `attendance_master_integrity`
- `inventory_system_reconciliation`
- `customer_deduplication_preparation`

Names and records are synthetic; domain labels exist only in profile data.

## Remaining product evolution

Resume-from-checkpoint currently means safe restart through an explicit retry of
the immutable request, not mid-stage continuation. Review-approved output
regeneration and richer review assignment are suitable follow-ups for Milestone 3.
