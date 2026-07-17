"""Ordered, checksummed, backup-first SQLite metadata migrations."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from packages.contracts import DatabaseMigrationReport, MigrationStepResult

M1A_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, locale TEXT NOT NULL,
    privacy_mode TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
    original_filename TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT NOT NULL, version INTEGER NOT NULL, project_id TEXT NOT NULL REFERENCES projects(id),
    display_name TEXT NOT NULL, configuration_json TEXT NOT NULL, created_at TEXT NOT NULL,
    PRIMARY KEY (id, version)
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), workflow_id TEXT NOT NULL,
    workflow_version INTEGER NOT NULL, status TEXT NOT NULL, record_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_project ON sources(project_id);
CREATE INDEX IF NOT EXISTS idx_workflows_project ON workflows(project_id);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id);
"""

M1B_JOB_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, run_id TEXT, status TEXT NOT NULL,
    request_json TEXT NOT NULL, record_json TEXT NOT NULL, correlation_id TEXT NOT NULL,
    cancel_requested INTEGER NOT NULL DEFAULT 0, retry_of TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL, event_json TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(job_id, sequence)
);
CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    checkpoint_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mapping_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, workflow_id TEXT NOT NULL,
    run_id TEXT, audit_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, sequence);
CREATE INDEX IF NOT EXISTS idx_checkpoints_job ON checkpoints(job_id, created_at);
CREATE INDEX IF NOT EXISTS idx_mapping_decisions_workflow ON mapping_decisions(workflow_id, created_at);
"""

VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


MIGRATIONS = (
    Migration(1, "milestone_1a_metadata", M1A_SCHEMA),
    Migration(2, "milestone_1b_jobs_checkpoints_mapping_history", M1B_JOB_SCHEMA),
)


class MigrationError(RuntimeError):
    pass


class SQLiteMigrationManager:
    def __init__(self, database_path: Path, migrations: tuple[Migration, ...] = MIGRATIONS) -> None:
        self.database_path = database_path
        self.migrations = migrations

    def _backup(self) -> Path:
        backup_root = self.database_path.parent / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        destination = backup_root / f"{self.database_path.stem}-pre-migration-{stamp}.sqlite3"
        source = sqlite3.connect(self.database_path)
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                raise MigrationError("DATABASE_BACKUP_INTEGRITY_FAILED")
        finally:
            target.close()
            source.close()
        return destination

    @staticmethod
    def _user_tables(connection: sqlite3.Connection) -> set[str]:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {str(row[0]) for row in rows}

    @staticmethod
    def _sql_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def migrate(self) -> DatabaseMigrationReport:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.database_path.exists() and self.database_path.stat().st_size > 0
        connection = sqlite3.connect(self.database_path)
        backup: Path | None = None
        steps: list[MigrationStepResult] = []
        try:
            tables = self._user_tables(connection)
            if existing and tables:
                backup = self._backup()
            connection.executescript(VERSION_TABLE)
            if "projects" in tables and "schema_migrations" not in tables:
                baseline = self.migrations[0]
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (baseline.version, baseline.name, baseline.checksum, datetime.now(UTC).isoformat()),
                )
                connection.commit()
            applied_rows = connection.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
            applied = {int(row[0]): str(row[1]) for row in applied_rows}
            from_version = max(applied, default=0)
            for migration in self.migrations:
                if migration.version in applied:
                    if applied[migration.version] != migration.checksum:
                        raise MigrationError(f"MIGRATION_CHECKSUM_MISMATCH: {migration.version}")
                    steps.append(
                        MigrationStepResult(
                            version=migration.version,
                            name=migration.name,
                            checksum=migration.checksum,
                            status="already_current",
                        )
                    )
                    continue
                applied_at = datetime.now(UTC).isoformat()
                record_sql = (
                    "INSERT INTO schema_migrations VALUES "
                    f"({migration.version}, {self._sql_literal(migration.name)}, "
                    f"{self._sql_literal(migration.checksum)}, {self._sql_literal(applied_at)});"
                )
                try:
                    connection.executescript(
                        f"BEGIN IMMEDIATE;\n{migration.sql}\n{record_sql}\nCOMMIT;"
                    )
                    steps.append(
                        MigrationStepResult(
                            version=migration.version,
                            name=migration.name,
                            checksum=migration.checksum,
                            status="applied",
                        )
                    )
                except sqlite3.Error as error:
                    connection.rollback()
                    raise MigrationError(
                        f"DATABASE_MIGRATION_FAILED: {migration.version}:{migration.name}"
                    ) from error
            final_row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            final_version = int(final_row[0] or 0)
            return DatabaseMigrationReport(
                from_version=from_version,
                to_version=final_version,
                backup_path=str(backup) if backup else None,
                steps=steps,
            )
        finally:
            connection.close()
