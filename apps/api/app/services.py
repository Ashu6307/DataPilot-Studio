"""Application services coordinating repositories and the generic engine."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from packages.contracts import (
    BatchCatalog,
    BatchCatalogRequest,
    CheckpointRecord,
    CompositionJobSubmission,
    CompositionPlan,
    CompositionPreview,
    CompositionPreviewRequest,
    DiscoveryOverrides,
    DiscoveryResult,
    FolderScanRequest,
    JobSubmission,
    PreviewRequest,
    PreviewResult,
    Project,
    ProjectCreate,
    ReconciliationJobSubmission,
    ReconciliationPreviewRequest,
    ReconciliationResult,
    ReconciliationWorkflow,
    RunRecord,
    RunRequest,
    SourceHandle,
    WorkflowConfiguration,
)
from packages.data_engine import (
    EngineRuntime,
    JobControl,
    RuntimeExecutionError,
    SourceFile,
    Workspace,
    discover_source,
)
from packages.data_engine.background import workflow_hash
from packages.data_engine.composition_background import composition_hash
from packages.data_engine.composition_runtime import CompositionRuntime
from packages.data_engine.multi_source import build_batch_catalog, scan_folder_paths
from packages.data_engine.reconciliation_runtime import ReconciliationRuntime
from packages.workflow_schema import assert_secret_free

from .repositories import MetadataRepository


class DataPilotService:
    def __init__(self, repository: MetadataRepository, workspace: Workspace) -> None:
        self.repository = repository
        self.workspace = workspace
        self.runtime = EngineRuntime(workspace)
        self.composition_runtime = CompositionRuntime(workspace)
        self.reconciliation_runtime = ReconciliationRuntime(workspace)

    def create_project(self, request: ProjectCreate) -> Project:
        return self.repository.create_project(Project(**request.model_dump()))

    def import_source(self, project_id: UUID, filename: str, media_type: str, stream: BinaryIO) -> SourceHandle:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as temporary:
                shutil.copyfileobj(stream, temporary)
                temp_path = Path(temporary.name)
            source = self.workspace.import_source(temp_path, filename)
            handle = SourceHandle(
                id=source.id,
                project_id=project_id,
                original_filename=filename,
                media_type=media_type,
                size_bytes=source.size_bytes,
                sha256=source.sha256,
            )
            return self.repository.save_source(handle)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _source(self, source_id: UUID) -> tuple[SourceHandle, SourceFile]:
        handle = self.repository.get_source(source_id)
        if handle is None:
            raise FileNotFoundError("SOURCE_NOT_FOUND")
        source = self.workspace.source_from_id(handle.id, handle.original_filename, handle.sha256)
        return handle, source

    def discover(self, source_id: UUID, overrides: DiscoveryOverrides) -> DiscoveryResult:
        handle, source = self._source(source_id)
        return discover_source(source, handle, overrides)

    def validate_workflow(self, workflow: WorkflowConfiguration) -> WorkflowConfiguration:
        assert_secret_free(workflow.model_dump(mode="json"))
        return workflow

    def save_workflow(self, workflow: WorkflowConfiguration) -> WorkflowConfiguration:
        self.validate_workflow(workflow)
        return self.repository.save_workflow(workflow)

    def preview(self, request: PreviewRequest) -> PreviewResult:
        _, source = self._source(request.source_id)
        return self.runtime.preview(source, request.workflow, request.limit)

    def run(self, request: RunRequest) -> RunRecord:
        handle, source = self._source(request.source_id)
        try:
            result = self.runtime.execute(source, handle, request.workflow)
        except RuntimeExecutionError as error:
            self.repository.save_run(error.record)
            raise
        return self.repository.save_run(result.record)

    def run_background(self, submission: JobSubmission, control: JobControl) -> RunRecord:
        request = submission.run
        handle, source = self._source(request.source_id)
        control.check_cancelled()
        control.store.save_checkpoint(
            CheckpointRecord(
                job_id=control.job_id,
                workflow_id=request.workflow.id,
                workflow_version=request.workflow.workflow_version,
                workflow_hash=workflow_hash(submission),
                source_fingerprint=source.sha256,
                completed_stage="request_validated",
                resumable=True,
            )
        )
        control.progress("source.discovery", 0, None, "Inspecting selected source structure")
        discovery = discover_source(source, handle, request.workflow.discovery_overrides)
        estimated_rows = discovery.tables[0].row_count_estimate if discovery.tables else 0
        control.check_cancelled()
        control.progress("workflow.execute", 0, estimated_rows, "Executing workflow in isolated run directory")
        try:
            result = self.runtime.execute(source, handle, request.workflow, control)
        except RuntimeExecutionError as error:
            self.repository.save_run(error.record)
            raise
        control.check_cancelled()
        self.repository.save_run(result.record)
        control.store.save_checkpoint(
            CheckpointRecord(
                job_id=control.job_id,
                workflow_id=request.workflow.id,
                workflow_version=request.workflow.workflow_version,
                workflow_hash=workflow_hash(submission),
                source_fingerprint=source.sha256,
                completed_stage="engine_completed",
                rows_processed=result.record.rows_read,
                artifact_path=result.record.artifacts[-1] if result.record.artifacts else None,
                resumable=False,
            )
        )
        return result.record

    def batch_catalog(self, request: BatchCatalogRequest) -> BatchCatalog:
        sources = [self._source(source_id) for source_id in request.source_ids]
        return build_batch_catalog(
            request.project_id,
            [(handle, source) for handle, source in sources],
            request.discovery_overrides,
            request.table_strategy,
            set(request.previous_fingerprints),
            explicit_table_ids=request.explicit_table_ids,
        )

    def scan_folder(self, request: FolderScanRequest) -> BatchCatalog:
        candidates = scan_folder_paths(request.configuration)
        imported: list[tuple[SourceHandle, SourceFile]] = []
        relative_paths: dict[UUID, str] = {}
        for candidate in candidates:
            with candidate.path.open("rb") as stream:
                handle = self.import_source(
                    request.project_id,
                    candidate.relative_path,
                    "text/csv" if candidate.path.suffix.casefold() == ".csv" else "application/vnd.ms-excel",
                    stream,
                )
            _, source = self._source(handle.id)
            imported.append((handle, source))
            relative_paths[handle.id] = candidate.relative_path
        catalog = build_batch_catalog(
            request.project_id,
            imported,
            request.discovery_overrides,
            request.configuration.table_strategy,
            set(request.configuration.previous_fingerprints),
            relative_paths,
            {
                source_id: request.configuration.explicit_table_ids[relative_path]
                for source_id, relative_path in relative_paths.items()
                if relative_path in request.configuration.explicit_table_ids
            },
        )
        return self.repository.save_folder_catalog(catalog, request.configuration.model_dump_json())

    def save_composition_plan(self, plan: CompositionPlan) -> CompositionPlan:
        assert_secret_free(plan.model_dump(mode="json"))
        return self.repository.save_composition_plan(plan)

    def preview_composition(self, request: CompositionPreviewRequest) -> CompositionPreview:
        explicit_tables = {
            source.source_id: source.table_id
            for source in request.plan.alignment.sources
            if source.table_id is not None
        }
        catalog_request = BatchCatalogRequest(
            project_id=request.plan.project_id,
            source_ids=request.plan.source_ids,
            discovery_overrides=request.plan.discovery_overrides,
            explicit_table_ids=explicit_tables,
        )
        catalog = self.batch_catalog(catalog_request)
        sources = {source_id: self._source(source_id) for source_id in request.plan.source_ids}
        return self.composition_runtime.preview(request.plan, catalog, sources, request.row_limit)

    def run_composition_background(self, submission: CompositionJobSubmission, control: JobControl) -> RunRecord:
        plan = submission.run.plan
        explicit_tables = {
            source.source_id: source.table_id
            for source in plan.alignment.sources
            if source.table_id is not None
        }
        catalog = self.batch_catalog(
            BatchCatalogRequest(
                project_id=plan.project_id,
                source_ids=plan.source_ids,
                discovery_overrides=plan.discovery_overrides,
                explicit_table_ids=explicit_tables,
            )
        )
        combined_fingerprint = hashlib.sha256(
            "".join(sorted(item.fingerprint for item in catalog.items)).encode("utf-8")
        ).hexdigest()
        control.store.save_checkpoint(
            CheckpointRecord(
                job_id=control.job_id,
                workflow_id=plan.id,
                workflow_version=plan.version,
                workflow_hash=composition_hash(submission),
                source_fingerprint=combined_fingerprint,
                completed_stage="composition_catalogued",
                resumable=True,
            )
        )
        sources = {source_id: self._source(source_id) for source_id in plan.source_ids}
        result = self.composition_runtime.execute(plan, catalog, sources, control)
        self.repository.save_run(result.record)
        self.repository.save_batch_manifest(plan.project_id, result.manifest)
        control.store.save_checkpoint(
            CheckpointRecord(
                job_id=control.job_id,
                workflow_id=plan.id,
                workflow_version=plan.version,
                workflow_hash=composition_hash(submission),
                source_fingerprint=combined_fingerprint,
                completed_stage="composition_completed",
                rows_processed=result.record.rows_read,
                artifact_path=result.record.artifacts[-1] if result.record.artifacts else None,
                resumable=False,
            )
        )
        return result.record

    def save_reconciliation_workflow(self, workflow: ReconciliationWorkflow) -> ReconciliationWorkflow:
        assert_secret_free(workflow.model_dump(mode="json"))
        return self.repository.save_reconciliation_workflow(workflow)

    def preview_reconciliation(self, request: ReconciliationPreviewRequest) -> ReconciliationResult:
        assert_secret_free(request.workflow.model_dump(mode="json"))
        _, left = self._source(request.workflow.left_dataset_id)
        _, right = self._source(request.workflow.right_dataset_id)
        return self.reconciliation_runtime.preview(request.workflow, left, right, request.row_limit)

    def run_reconciliation_background(
        self,
        submission: ReconciliationJobSubmission,
        control: JobControl,
    ) -> RunRecord:
        workflow = submission.run.workflow
        assert_secret_free(workflow.model_dump(mode="json"))
        left = self._source(workflow.left_dataset_id)
        right = self._source(workflow.right_dataset_id)
        combined_fingerprint = hashlib.sha256(
            "".join(sorted([left[0].sha256, right[0].sha256])).encode("utf-8")
        ).hexdigest()
        workflow_digest = hashlib.sha256(workflow.model_dump_json().encode("utf-8")).hexdigest()
        control.store.save_checkpoint(
            CheckpointRecord(
                job_id=control.job_id,
                workflow_id=workflow.id,
                workflow_version=workflow.version,
                workflow_hash=workflow_digest,
                source_fingerprint=combined_fingerprint,
                completed_stage="reconciliation_inputs_validated",
                resumable=True,
            )
        )
        result = self.reconciliation_runtime.execute(workflow, left, right, control)
        self.repository.save_run(result.record)
        self.repository.save_reconciliation_run(result.reconciliation_record)
        self.repository.save_review_items(result.result.review_items)
        self.repository.save_reconciliation_manifest(result.manifest)
        control.store.save_checkpoint(
            CheckpointRecord(
                job_id=control.job_id,
                workflow_id=workflow.id,
                workflow_version=workflow.version,
                workflow_hash=workflow_digest,
                source_fingerprint=combined_fingerprint,
                completed_stage="reconciliation_completed",
                rows_processed=result.record.rows_read,
                artifact_path=result.record.artifacts[-1] if result.record.artifacts else None,
                resumable=False,
            )
        )
        return result.record
