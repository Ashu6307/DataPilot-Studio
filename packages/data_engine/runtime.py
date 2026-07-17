"""Workflow preview and full run orchestration."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import polars as pl

from packages.contracts import (
    OperationMetric,
    PreviewResult,
    RunRecord,
    RunStatus,
    Severity,
    SourceHandle,
    ValidationFinding,
    WorkflowConfiguration,
)
from packages.data_engine.discovery import read_selected_table
from packages.data_engine.exporter import export_workbook
from packages.data_engine.mapping import apply_mapping
from packages.data_engine.operations import apply_operation
from packages.data_engine.safety import SourceFile, Workspace, sha256_file
from packages.data_engine.validation import validate_table
from packages.workflow_schema import assert_secret_free


@dataclass(slots=True)
class RuntimeResult:
    record: RunRecord
    findings: list[ValidationFinding]
    rejected_rows: list[dict[str, object]]
    run_directory: Path


class RuntimeExecutionError(RuntimeError):
    """A failed run that still carries auditable run evidence."""

    def __init__(self, message: str, record: RunRecord, run_directory: Path) -> None:
        super().__init__(message)
        self.record = record
        self.run_directory = run_directory


@dataclass(slots=True)
class PreparedResult:
    processed: pl.DataFrame
    rejected: list[dict[str, object]]
    findings: list[ValidationFinding]
    metrics: list[OperationMetric]
    counts: dict[str, int]


class EngineRuntime:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def _prepare(self, source: SourceFile, workflow: WorkflowConfiguration, limit: int | None) -> PreparedResult:
        assert_secret_free(workflow.model_dump(mode="json"))
        source.assert_unchanged()
        raw = read_selected_table(source, workflow.discovery_overrides, limit)
        rows_read = raw.height
        table = apply_mapping(raw, workflow.mapping)
        metrics: list[OperationMetric] = []
        rows_filtered = 0
        for node in workflow.operations:
            if not node.enabled:
                continue
            execution = apply_operation(table, node)
            table = execution.table
            metrics.append(execution.metric)
            rows_filtered += execution.filtered_rows
        findings = validate_table(table, workflow.validation_rules)
        reject_ids = {
            int(item.row_identifier)
            for item in findings
            if item.severity in {Severity.ERROR, Severity.BLOCKING} and item.row_identifier.isdigit()
        }
        records = table.to_dicts()
        reason_map: dict[int, list[str]] = {}
        for finding in findings:
            if finding.row_identifier.isdigit():
                reason_map.setdefault(int(finding.row_identifier), []).append(finding.reason_code)
        rejected: list[dict[str, object]] = []
        accepted: list[dict[str, object]] = []
        for record in records:
            row_id = int(record.get("__row_id", 0))
            if row_id in reject_ids:
                rejected.append({**record, "__reason_codes": ",".join(reason_map.get(row_id, []))})
            else:
                accepted.append(record)
        processed = pl.DataFrame(accepted, schema=table.schema) if accepted else table.clear()
        counts = {
            "rows_read": rows_read,
            "rows_written": processed.height,
            "rows_rejected": len(rejected),
            "rows_filtered": rows_filtered,
        }
        if counts["rows_read"] != counts["rows_written"] + counts["rows_rejected"] + counts["rows_filtered"]:
            raise RuntimeError(f"ROW_RECONCILIATION_FAILED: {counts}")
        source.assert_unchanged()
        return PreparedResult(processed, rejected, findings, metrics, counts)

    def preview(self, source: SourceFile, workflow: WorkflowConfiguration, limit: int = 50) -> PreviewResult:
        prepared = self._prepare(source, workflow, limit)
        return PreviewResult(
            rows=prepared.processed.to_dicts(),
            rejected_rows=prepared.rejected,
            findings=prepared.findings,
            operation_metrics=prepared.metrics,
            **prepared.counts,
        )

    def execute(self, source: SourceFile, handle: SourceHandle, workflow: WorkflowConfiguration) -> RuntimeResult:
        run_id = uuid4()
        run_directory = self.workspace.create_run_directory(run_id)
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        snapshot = run_directory / "config-snapshot" / "workflow.json"
        snapshot.write_text(workflow.model_dump_json(indent=2), encoding="utf-8")
        try:
            prepared = self._prepare(source, workflow, None)
            workbook = export_workbook(
                run_directory / "outputs",
                run_id,
                source,
                workflow,
                prepared.processed,
                prepared.rejected,
                prepared.findings,
                prepared.metrics,
                prepared.counts,
            )
            source.assert_unchanged()
            blocking = any(item.severity == Severity.BLOCKING for item in prepared.findings)
            status = RunStatus.PARTIAL if blocking else RunStatus.SUCCEEDED
            manifest = {
                "schema_version": "1.0",
                "run_id": str(run_id),
                "status": status,
                "workflow_id": str(workflow.id),
                "workflow_version": workflow.workflow_version,
                "source": {
                    "id": str(handle.id),
                    "filename": handle.original_filename,
                    "sha256": source.sha256,
                    "size_bytes": source.size_bytes,
                },
                "counts": prepared.counts,
                "artifacts": [{"name": workbook.name, "sha256": sha256_file(workbook)}],
            }
            manifest_path = run_directory / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
            json.loads(manifest_path.read_text(encoding="utf-8"))
            duration = int((time.perf_counter() - started) * 1000)
            record = RunRecord(
                id=run_id,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                workflow_version=workflow.workflow_version,
                status=status,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                source_filename=handle.original_filename,
                source_fingerprint=source.sha256,
                **prepared.counts,
                warnings=[item.explanation for item in prepared.findings if item.severity == Severity.WARNING],
                operations=prepared.metrics,
                artifacts=[str(workbook), str(manifest_path)],
                duration_ms=duration,
            )
            return RuntimeResult(record, prepared.findings, prepared.rejected, run_directory)
        except Exception as error:
            source.assert_unchanged()
            failure_manifest = run_directory / "manifest.json"
            failure_manifest.write_text(
                json.dumps({"schema_version": "1.0", "run_id": str(run_id), "status": "failed"}, indent=2),
                encoding="utf-8",
            )
            duration = int((time.perf_counter() - started) * 1000)
            record = RunRecord(
                id=run_id,
                project_id=workflow.project_id,
                workflow_id=workflow.id,
                workflow_version=workflow.workflow_version,
                status=RunStatus.FAILED,
                started_at=started_at,
                ended_at=datetime.now(UTC),
                source_filename=handle.original_filename,
                source_fingerprint=source.sha256,
                errors=[type(error).__name__],
                artifacts=[str(failure_manifest)],
                duration_ms=duration,
            )
            raise RuntimeExecutionError(str(error), record, run_directory) from error
