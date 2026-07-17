from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from apps.api.app.database import Database
from apps.api.app.migrations import M1A_SCHEMA, Migration, MigrationError, SQLiteMigrationManager
from packages.contracts import WorkflowConfiguration
from packages.workflow_schema import WorkflowMigrationError, migrate_workflow_file, migrate_workflow_payload


def test_existing_m1a_database_is_backed_up_and_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "metadata.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(M1A_SCHEMA)
    connection.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
        ("p", "Existing", "en-IN", "local_only", "2026-07-17", "2026-07-17"),
    )
    connection.commit()
    connection.close()

    database = Database(path)
    database.initialize()
    assert database.last_migration_report is not None
    assert database.last_migration_report.to_version == 2
    assert database.last_migration_report.backup_path is not None
    assert Path(database.last_migration_report.backup_path).exists()
    with database.connect() as upgraded:
        tables = {
            row[0]
            for row in upgraded.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"schema_migrations", "jobs", "job_events", "checkpoints", "mapping_decisions"} <= tables
        assert upgraded.execute("SELECT name FROM projects WHERE id = 'p'").fetchone()[0] == "Existing"


def test_failed_database_migration_rolls_back_and_preserves_backup(tmp_path: Path) -> None:
    path = tmp_path / "metadata.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(M1A_SCHEMA)
    connection.commit()
    connection.close()
    bad = (
        Migration(1, "milestone_1a_metadata", M1A_SCHEMA),
        Migration(2, "invalid", "CREATE TABLE partial(id TEXT); INVALID SQL;"),
    )
    with pytest.raises(MigrationError, match="DATABASE_MIGRATION_FAILED"):
        SQLiteMigrationManager(path, bad).migrate()
    assert list((tmp_path / "backups").glob("*.sqlite3"))
    check = sqlite3.connect(path)
    try:
        assert check.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 2"
        ).fetchone()[0] == 0
        assert check.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'partial'"
        ).fetchone()[0] == 0
    finally:
        check.close()


def test_workflow_v1_migrates_with_report_and_file_backup(
    workflow: WorkflowConfiguration, tmp_path: Path
) -> None:
    payload = workflow.model_dump(mode="json")
    payload["schema_version"] = "1.0"
    payload.pop("calculations", None)
    discovery = payload["discovery_overrides"]
    for key in (
        "header_rows",
        "table_id",
        "profile_sample_rows",
        "max_header_levels",
        "header_flattening_separator",
    ):
        discovery.pop(key, None)
    migrated, report = migrate_workflow_payload(payload)
    assert migrated["schema_version"] == "1.1"
    assert "calculations" in report.changed_paths
    WorkflowConfiguration.model_validate(migrated)

    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")
    file_report = migrate_workflow_file(path, tmp_path / "backups")
    assert file_report.backup_path and Path(file_report.backup_path).exists()
    loaded = WorkflowConfiguration.model_validate_json(path.read_text(encoding="utf-8"))
    assert loaded.schema_version == "1.1"


def test_future_workflow_version_blocks_actionably(workflow: WorkflowConfiguration) -> None:
    payload = workflow.model_dump(mode="json")
    payload["schema_version"] = "2.0"
    with pytest.raises(WorkflowMigrationError, match="WORKFLOW_VERSION_UNSUPPORTED"):
        migrate_workflow_payload(payload)
