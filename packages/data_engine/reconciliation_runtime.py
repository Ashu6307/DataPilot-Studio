"""Preview and full-run orchestration for reconciliation workflows."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from packages.contracts import (
    CheckpointRecord,
    ReconciliationExportManifest,
    ReconciliationResult,
    ReconciliationRunRecord,
    ReconciliationWorkflow,
    RunRecord,
    SourceHandle,
)
from packages.data_engine.comparison import compare_datasets
from packages.data_engine.discovery import read_selected_table
from packages.data_engine.reconciliation import reconcile_datasets
from packages.data_engine.reconciliation_exporter import export_reconciliation_evidence
from packages.data_engine.referential_integrity import check_referential_integrity
from packages.data_engine.safety import SourceFile, Workspace

if TYPE_CHECKING:
    from packages.data_engine.background import JobControl


@dataclass(slots=True)
class ReconciliationRuntimeResult:
    record: RunRecord
    reconciliation_record: ReconciliationRunRecord
    result: ReconciliationResult
    manifest: ReconciliationExportManifest
    run_directory: Path


class ReconciliationRuntime:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def preview(
        self,
        workflow: ReconciliationWorkflow,
        left_source: SourceFile,
        right_source: SourceFile,
        limit: int,
    ) -> ReconciliationResult:
        left_source.assert_unchanged()
        right_source.assert_unchanged()
        left = read_selected_table(left_source, workflow.left_discovery, limit)
        right = read_selected_table(right_source, workflow.right_discovery, limit)
        result = reconcile_datasets(left, right, workflow)
        if workflow.comparison is not None:
            result.comparison_result = compare_datasets(left, right, workflow.comparison)
        if workflow.referential_integrity is not None:
            result.integrity_result = check_referential_integrity(left, right, workflow.referential_integrity)
        left_source.assert_unchanged()
        right_source.assert_unchanged()
        return result

    def execute(
        self,
        workflow: ReconciliationWorkflow,
        left: tuple[SourceHandle, SourceFile],
        right: tuple[SourceHandle, SourceFile],
        control: JobControl | None = None,
    ) -> ReconciliationRuntimeResult:
        run_id = uuid4()
        run_directory = self.workspace.create_run_directory(run_id)
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        snapshot = run_directory / "config-snapshot" / "reconciliation-workflow.json"
        snapshot.write_text(workflow.model_dump_json(indent=2), encoding="utf-8")
        left_handle, left_source = left
        right_handle, right_source = right
        left_source.assert_unchanged()
        right_source.assert_unchanged()
        left_table = read_selected_table(left_source, workflow.left_discovery)
        right_table = read_selected_table(right_source, workflow.right_discovery)
        total_rows = left_table.height + right_table.height
        combined_fingerprint = hashlib.sha256(
            "".join(sorted([left_handle.sha256, right_handle.sha256])).encode("utf-8")
        ).hexdigest()
        workflow_digest = hashlib.sha256(workflow.model_dump_json().encode("utf-8")).hexdigest()
        completed_stage_count = 0

        def cancel() -> None:
            if control is not None:
                control.check_cancelled()

        def progress(stage_id: str, completed: int, total: int, message: str) -> None:
            nonlocal completed_stage_count
            if control is None:
                return
            rows_processed = total_rows if total <= 0 else int(total_rows * completed / total)
            control.progress(
                f"reconciliation.{stage_id}",
                rows_processed,
                total_rows,
                message,
            )
            if completed > completed_stage_count:
                completed_stage_count = completed
                control.store.save_checkpoint(
                    CheckpointRecord(
                        job_id=control.job_id,
                        workflow_id=workflow.id,
                        workflow_version=workflow.version,
                        workflow_hash=workflow_digest,
                        source_fingerprint=combined_fingerprint,
                        completed_stage=stage_id,
                        rows_processed=rows_processed,
                        resumable=True,
                    )
                )

        result = reconcile_datasets(
            left_table,
            right_table,
            workflow,
            run_id=run_id,
            cancel=cancel,
            progress=progress,
        )
        if workflow.comparison is not None:
            result.comparison_result = compare_datasets(left_table, right_table, workflow.comparison)
        if workflow.referential_integrity is not None:
            result.integrity_result = check_referential_integrity(
                left_table, right_table, workflow.referential_integrity
            )
        cancel()
        if control is not None:
            control.progress("reconciliation.export", total_rows, total_rows, "Writing evidence outputs")
        manifest = export_reconciliation_evidence(
            run_directory / "outputs", result, workflow, result.integrity_result
        )
        cancel()
        left_source.assert_unchanged()
        right_source.assert_unchanged()
        output_paths = sorted(path for path in (run_directory / "outputs").rglob("*") if path.is_file())
        for path in output_paths:
            if not path.read_bytes() and path.stat().st_size > 0:
                raise RuntimeError("RECONCILIATION_OUTPUT_UNREADABLE")
        root_manifest = run_directory / "manifest.json"
        root_manifest.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        json.loads(root_manifest.read_text(encoding="utf-8"))
        artifacts = [str(path) for path in output_paths] + [str(root_manifest)]
        source_filenames = f"{left_handle.original_filename} + {right_handle.original_filename}"
        record = RunRecord(
            id=run_id,
            project_id=workflow.project_id,
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status=result.status,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            source_filename=source_filenames,
            source_fingerprint=combined_fingerprint,
            rows_read=total_rows,
            rows_written=total_rows,
            rows_rejected=0,
            warnings=result.warnings,
            artifacts=artifacts,
            duration_ms=int((time.perf_counter() - started) * 1_000),
        )
        reconciliation_record = ReconciliationRunRecord(
            run_id=run_id,
            project_id=workflow.project_id,
            workflow_id=workflow.id,
            workflow_version=workflow.version,
            status=result.status,
            summary=result.summary,
            audit=result.audit,
            artifacts=artifacts,
        )
        return ReconciliationRuntimeResult(
            record=record,
            reconciliation_record=reconciliation_record,
            result=result,
            manifest=manifest,
            run_directory=run_directory,
        )
