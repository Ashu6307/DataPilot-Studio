"""Preview and full-run orchestration for generic composition plans."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import polars as pl

from packages.contracts import (
    AppendConfiguration,
    BatchCatalog,
    BatchManifest,
    CompositionOperation,
    CompositionPlan,
    CompositionPreview,
    RunRecord,
    RunStatus,
    SchemaAlignmentMatrix,
    SourceHandle,
)
from packages.data_engine.batch_exporter import export_batch_evidence, export_split_outputs
from packages.data_engine.composition import (
    CompositionResult,
    aggregate_table,
    append_tables,
    join_tables,
    pivot_table,
    unpivot_table,
)
from packages.data_engine.discovery import read_selected_table
from packages.data_engine.safety import SourceFile, Workspace
from packages.data_engine.schema_alignment import align_table, build_alignment_matrix

if TYPE_CHECKING:
    from packages.data_engine.background import JobControl


@dataclass(slots=True)
class CompositionRuntimeResult:
    record: RunRecord
    manifest: BatchManifest
    run_directory: Path


class CompositionRuntime:
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace

    def _aligned_tables(
        self,
        plan: CompositionPlan,
        catalog: BatchCatalog,
        sources: dict[UUID, tuple[SourceHandle, SourceFile]],
        limit: int | None,
        control: JobControl | None = None,
    ) -> tuple[dict[UUID, pl.DataFrame], SchemaAlignmentMatrix]:
        matrix = build_alignment_matrix(catalog, plan.alignment)
        if matrix.blocked:
            raise ValueError("SCHEMA_ALIGNMENT_BLOCKED")
        item_by_id = {item.source_id: item for item in catalog.items}
        tables: dict[UUID, pl.DataFrame] = {}
        processed = 0
        total = max(1, catalog.total_row_estimate)
        source_plan_by_id = {item.source_id: item for item in plan.alignment.sources}
        for source_id in matrix.eligible_source_ids:
            if control is not None:
                control.check_cancelled()
                control.progress("composition.source_read", processed, total, f"Reading source {source_id}")
            handle, source = sources[source_id]
            item = item_by_id[source_id]
            alignment_source = source_plan_by_id[source_id]
            overrides = plan.discovery_overrides.model_copy(
                update={"table_id": alignment_source.table_id or item.table_id}
            )
            raw = read_selected_table(source, overrides, limit)
            tables[source_id] = align_table(
                raw,
                source_id,
                item.filename,
                item.table_id or "selected-table",
                plan.alignment,
            )
            processed += raw.height
        return tables, matrix

    @staticmethod
    def _compose(plan: CompositionPlan, tables: dict[UUID, pl.DataFrame]) -> CompositionResult:
        ordered = [tables[source_id] for source_id in plan.source_ids if source_id in tables]
        if not ordered:
            raise ValueError("COMPOSITION_HAS_NO_ELIGIBLE_INPUTS")
        if plan.operation in {CompositionOperation.APPEND, CompositionOperation.UNION}:
            assert plan.append is not None
            return append_tables(ordered, plan.append)
        if plan.operation == CompositionOperation.JOIN:
            assert plan.join is not None
            return join_tables(tables[plan.join.left_source_id], tables[plan.join.right_source_id], plan.join)
        base = append_tables(ordered, plan.append or AppendConfiguration()).table
        if plan.operation == CompositionOperation.AGGREGATE:
            assert plan.aggregation is not None
            return aggregate_table(base, plan.aggregation)
        if plan.operation == CompositionOperation.PIVOT:
            assert plan.pivot is not None
            return pivot_table(base, plan.pivot)
        if plan.operation == CompositionOperation.UNPIVOT:
            assert plan.unpivot is not None
            return unpivot_table(base, plan.unpivot)
        raise ValueError(f"COMPOSITION_OPERATION_UNSUPPORTED: {plan.operation}")

    def preview(
        self,
        plan: CompositionPlan,
        catalog: BatchCatalog,
        sources: dict[UUID, tuple[SourceHandle, SourceFile]],
        limit: int,
    ) -> CompositionPreview:
        tables, matrix = self._aligned_tables(plan, catalog, sources, limit)
        result = self._compose(plan, tables)
        diagnostics = result.join_diagnostics
        return CompositionPreview(
            operation=plan.operation,
            rows=result.table.head(limit).to_dicts(),
            alignment=matrix,
            input_rows=result.input_rows,
            output_rows=result.table.height,
            rejected_rows=result.rejected.height,
            duplicate_rows=result.duplicate_rows,
            group_count=result.table.height if plan.operation == CompositionOperation.AGGREGATE else 0,
            null_impact=sum(result.table[column].null_count() for column in result.table.columns),
            estimated_peak_memory_bytes=max(1, catalog.total_row_estimate) * max(1, result.table.width) * 64,
            generated_columns=(result.table.width if plan.operation == CompositionOperation.PIVOT else 0),
            join_diagnostics=diagnostics,
            warnings=[*matrix.warnings, *result.warnings],
        )

    def execute(
        self,
        plan: CompositionPlan,
        catalog: BatchCatalog,
        sources: dict[UUID, tuple[SourceHandle, SourceFile]],
        control: JobControl | None = None,
    ) -> CompositionRuntimeResult:
        run_id = uuid4()
        run_directory = self.workspace.create_run_directory(run_id)
        started_at = datetime.now(UTC)
        started = time.perf_counter()
        snapshot = run_directory / "config-snapshot" / "composition-plan.json"
        snapshot.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        for _, source in sources.values():
            source.assert_unchanged()
        tables, matrix = self._aligned_tables(plan, catalog, sources, None, control)
        if control is not None:
            control.check_cancelled()
            control.progress("composition.execute", 0, catalog.total_row_estimate, f"Executing {plan.operation}")
        result = self._compose(plan, tables)
        if control is not None:
            control.check_cancelled()
            control.progress(
                "composition.package",
                result.input_rows,
                max(result.input_rows, catalog.total_row_estimate),
                "Writing derived evidence package",
            )
        outputs = export_batch_evidence(
            run_directory / "outputs",
            run_id,
            plan,
            catalog,
            matrix,
            result.table,
            result.rejected,
            result.review,
            result.warnings,
            result.left_unmatched,
            result.right_unmatched,
        )
        if plan.split is not None:
            if control is not None:
                control.check_cancelled()
                control.progress(
                    "composition.split",
                    result.input_rows,
                    result.input_rows,
                    "Writing configured split outputs",
                )
            split_entries = export_split_outputs(
                run_directory / "outputs" / "splits",
                run_id,
                result.table,
                plan.split,
                started_at.date(),
            )
            outputs.extend(
                entry.model_copy(update={"relative_path": f"splits/{entry.relative_path}"}) for entry in split_entries
            )
        if control is not None:
            control.check_cancelled()
        for _, source in sources.values():
            source.assert_unchanged()
        partial = bool(matrix.rejected_source_ids or matrix.quarantined_source_ids or catalog.files_quarantined)
        status = RunStatus.PARTIAL if partial else RunStatus.SUCCEEDED
        routed_review = (
            result.review.height if plan.operation in {CompositionOperation.APPEND, CompositionOperation.UNION} else 0
        )
        filtered = (
            max(0, result.input_rows - result.table.height - result.rejected.height - routed_review)
            if plan.operation in {CompositionOperation.APPEND, CompositionOperation.UNION}
            else 0
        )
        reconciliation = {
            "input_rows": result.input_rows,
            "output_rows": result.table.height,
            "rejected_rows": result.rejected.height,
            "review_rows": routed_review,
            "filtered_rows": filtered,
            "net_row_change": result.table.height - result.input_rows,
        }
        source_fingerprint = hashlib.sha256(
            "".join(sorted(item.fingerprint for item in catalog.items)).encode("utf-8")
        ).hexdigest()
        manifest = BatchManifest(
            run_id=run_id,
            plan_id=plan.id,
            plan_version=plan.version,
            status=status,
            source_items=catalog.items,
            outputs=outputs,
            files_considered=catalog.files_considered,
            files_accepted=len(matrix.eligible_source_ids),
            files_rejected=catalog.files_considered - len(matrix.eligible_source_ids),
            rows_read=result.input_rows,
            rows_output=result.table.height,
            rows_rejected=result.rejected.height,
            rows_review=routed_review,
            rows_filtered=filtered,
            duplicate_rows=result.duplicate_rows,
            source_row_counts={str(source_id): table.height for source_id, table in tables.items()},
            row_reconciliation=reconciliation,
            warnings=[*catalog.warnings, *matrix.warnings, *result.warnings],
        )
        manifest_path = run_directory / "manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        json.loads(manifest_path.read_text(encoding="utf-8"))
        record = RunRecord(
            id=run_id,
            project_id=plan.project_id,
            workflow_id=plan.id,
            workflow_version=plan.version,
            status=status,
            started_at=started_at,
            ended_at=datetime.now(UTC),
            source_filename=f"{catalog.files_considered} source files",
            source_fingerprint=source_fingerprint,
            rows_read=result.input_rows,
            rows_written=result.table.height,
            rows_rejected=result.rejected.height,
            warnings=manifest.warnings,
            artifacts=[str(run_directory / "outputs" / item.relative_path) for item in outputs] + [str(manifest_path)],
            duration_ms=int((time.perf_counter() - started) * 1_000),
        )
        return CompositionRuntimeResult(record, manifest, run_directory)
