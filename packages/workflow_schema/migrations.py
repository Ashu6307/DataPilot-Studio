"""Pure workflow compatibility migrations with explicit backup/reporting."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.contracts import WorkflowConfiguration, WorkflowMigrationReport


class WorkflowMigrationError(ValueError):
    pass


def migrate_workflow_payload(
    payload: dict[str, Any], target_version: str = "1.2"
) -> tuple[dict[str, Any], WorkflowMigrationReport]:
    migrated = deepcopy(payload)
    source_version = str(migrated.get("schema_version", "1.0"))
    original_version = source_version
    if source_version not in {"1.0", "1.1", "1.2"}:
        raise WorkflowMigrationError(
            f"WORKFLOW_VERSION_UNSUPPORTED: {source_version}; supported versions are 1.0, 1.1 and 1.2"
        )
    if target_version not in {"1.1", "1.2"}:
        raise WorkflowMigrationError(f"WORKFLOW_MIGRATION_TARGET_UNSUPPORTED: {target_version}")
    if source_version == "1.2" and target_version != "1.2":
        raise WorkflowMigrationError("WORKFLOW_DOWNGRADE_NOT_SUPPORTED")
    changed: list[str] = []
    if source_version == "1.0":
        migrated["schema_version"] = "1.1"
        changed.append("schema_version")
        discovery = migrated.setdefault("discovery_overrides", {})
        defaults: dict[str, Any] = {
            "header_rows": None,
            "table_id": None,
            "profile_sample_rows": 10_000,
            "max_header_levels": 3,
            "header_flattening_separator": ".",
        }
        for key, value in defaults.items():
            if key not in discovery:
                discovery[key] = value
                changed.append(f"discovery_overrides.{key}")
        if "calculations" not in migrated:
            migrated["calculations"] = []
            changed.append("calculations")
        source_version = "1.1"
    if source_version == "1.1" and target_version == "1.2":
        migrated["schema_version"] = "1.2"
        changed.append("schema_version")
        if "composition_plan_id" not in migrated:
            migrated["composition_plan_id"] = None
            changed.append("composition_plan_id")
        if "composition_plan_version" not in migrated:
            migrated["composition_plan_version"] = None
            changed.append("composition_plan_version")
    WorkflowConfiguration.model_validate(migrated)
    return migrated, WorkflowMigrationReport(
        from_version=original_version,
        to_version=target_version,
        changed_paths=changed,
    )


def migrate_workflow_file(path: Path, backup_directory: Path) -> WorkflowMigrationReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise WorkflowMigrationError("WORKFLOW_ROOT_MUST_BE_OBJECT")
    migrated, report = migrate_workflow_payload(payload)
    if not report.changed_paths:
        return report
    backup_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_directory / f"{path.stem}-v{report.from_version}-{stamp}{path.suffix}"
    shutil.copy2(path, backup)
    temporary = path.with_suffix(f"{path.suffix}.migrating")
    temporary.write_text(
        json.dumps(migrated, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    WorkflowConfiguration.model_validate_json(temporary.read_text(encoding="utf-8"))
    temporary.replace(path)
    return report.model_copy(update={"backup_path": str(backup)})
