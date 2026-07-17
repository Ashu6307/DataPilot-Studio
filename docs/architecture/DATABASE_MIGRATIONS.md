# Database Migrations

SQLite metadata schema changes use ordered migrations with version, name, checksum, and applied timestamp in `schema_migrations`.

Before an upgrade the application closes active writes, creates and verifies a timestamped backup below workspace backups, then applies each migration in one transaction. A failure rolls back the migration, preserves the backup, and prevents application startup with a structured error. Destructive column/table removal is not performed silently.

The M1A baseline is recognised from its existing tables and recorded as version 1. M1B adds job, progress event, checkpoint, and mapping-decision metadata. M2A adds composition-plan metadata. M2B schema version 4 adds reconciliation workflow/run metadata, bounded review items, append-only review decision events, decision-memory audit events, and export manifests. Raw uploaded files and complete source datasets remain outside SQLite.

Workflow JSON uses a separate pure migration chain. M2B advances compatible
workflow envelopes from `1.2` to `1.3`, adding reconciliation workflow identity
and version fields without mutating prior mapping or composition definitions.
# Milestone 3A additions

SQLite schema version 5 adds versioned DAG workflows/subflows, execution plans,
runs, node attempts, artifact metadata, manual checkpoints, immutable decision
events, and evidence-package versions. Ordered schema version 6 adds persisted
M2B reconciliation-result artifact links for review-aware regeneration. Upgrade from version 4 is backup-first and
transactional; failure leaves the version row and partial tables rolled back.

Portable workflow schema 1.4 migrates from 1.3 by adding nullable
`dag_workflow_id` and `dag_workflow_version` references. File migration writes a
timestamped backup, validates a temporary file, and atomically replaces the
source only after success. Downgrades and future unknown versions are rejected.
