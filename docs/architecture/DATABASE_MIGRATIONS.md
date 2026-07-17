# Database Migrations

SQLite metadata schema changes use ordered migrations with version, name, checksum, and applied timestamp in `schema_migrations`.

Before an upgrade the application closes active writes, creates and verifies a timestamped backup below workspace backups, then applies each migration in one transaction. A failure rolls back the migration, preserves the backup, and prevents application startup with a structured error. Destructive column/table removal is not performed silently.

The M1A baseline is recognised from its existing tables and recorded as version 1. M1B adds job, progress event, checkpoint, and mapping-decision metadata without storing complete source rows.
