# Database Migrations

SQLite metadata schema changes use ordered migrations with version, name, checksum, and applied timestamp in `schema_migrations`.

Before an upgrade the application closes active writes, creates and verifies a timestamped backup below workspace backups, then applies each migration in one transaction. A failure rolls back the migration, preserves the backup, and prevents application startup with a structured error. Destructive column/table removal is not performed silently.

The M1A baseline is recognised from its existing tables and recorded as version 1. M1B adds job, progress event, checkpoint, and mapping-decision metadata. M2A adds composition-plan metadata. M2B schema version 4 adds reconciliation workflow/run metadata, bounded review items, append-only review decision events, decision-memory audit events, and export manifests. Raw uploaded files and complete source datasets remain outside SQLite.

Workflow JSON uses a separate pure migration chain. M2B advances compatible
workflow envelopes from `1.2` to `1.3`, adding reconciliation workflow identity
and version fields without mutating prior mapping or composition definitions.
