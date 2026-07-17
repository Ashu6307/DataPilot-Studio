# ADR-007: Explicit reversible compatibility migrations

Status: Accepted — 2026-07-17

## Decision

Use checksummed ordered SQLite migrations with verified pre-upgrade backups, and pure version-to-version workflow migration functions that emit reports and preserve the original definition.

## Consequences

Unknown future versions block safely. Migration failures do not silently corrupt metadata or workflow evidence.
