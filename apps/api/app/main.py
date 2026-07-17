"""FastAPI entrypoint for the local DataPilot service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from packages.contracts import (
    BackgroundJobRecord,
    BatchCatalog,
    BatchCatalogRequest,
    BatchManifest,
    CheckpointRecord,
    CompositionJobSubmission,
    CompositionPlan,
    CompositionPreview,
    CompositionPreviewRequest,
    CompositionRunRequest,
    DagJobSubmission,
    DagRunRecord,
    DagRunRequest,
    DagValidationResult,
    DagWorkflow,
    DecisionMemory,
    DecisionMemoryDeactivateRequest,
    DiscoveryOverrides,
    DiscoveryResult,
    EvidencePackageVersion,
    EvidenceRegenerationRequest,
    ExecutionPlan,
    FolderScanRequest,
    JobProgressEvent,
    JobSubmission,
    ManualCheckpoint,
    ManualCheckpointDecision,
    MappingRepairRequest,
    MappingRepairResponse,
    MappingSet,
    NodeCapability,
    NodeRunRecord,
    PreviewRequest,
    PreviewResult,
    Project,
    ProjectCreate,
    ReconciliationExportManifest,
    ReconciliationJobSubmission,
    ReconciliationPreviewRequest,
    ReconciliationResult,
    ReconciliationRunRecord,
    ReconciliationRunRequest,
    ReconciliationWorkflow,
    ReviewDecisionEvent,
    ReviewQueueItem,
    RunRecord,
    RunRequest,
    SchemaDriftRequest,
    SchemaDriftResult,
    SourceHandle,
    StructureComparisonRequest,
    StructureComparisonResult,
    SubflowDefinition,
    WorkflowCloneRequest,
    WorkflowConfiguration,
    WorkflowDiff,
    WorkflowDiffRequest,
    WorkflowLifecycle,
    WorkflowPlanRequest,
    WorkflowRestoreRequest,
    WorkflowVersionRequest,
)
from packages.data_engine import LocalJobExecutor, Workspace
from packages.data_engine.comparison import compare_structures
from packages.data_engine.composition_background import LocalCompositionJobExecutor
from packages.data_engine.reconciliation_background import LocalReconciliationJobExecutor
from packages.data_engine.schema_drift import analyze_schema_drift, repair_mapping
from packages.workflow_dag import build_execution_plan, default_registry, diff_workflows, validate_dag
from packages.workflow_dag.runtime import LocalDagExecutor

from .composition_job_store import SQLiteCompositionJobStore
from .config import load_settings
from .dag_adapters import application_adapter_registry
from .dag_repository import SQLiteDagRepository
from .database import Database
from .evidence_regeneration import EvidenceRegenerationService
from .job_store import SQLiteJobStore
from .reconciliation_job_store import SQLiteReconciliationJobStore
from .repositories import SQLiteMetadataRepository
from .services import DataPilotService

settings = load_settings()
database = Database(settings.database)
repository = SQLiteMetadataRepository(database)
workspace = Workspace(settings.workspace)
service = DataPilotService(repository, workspace)
job_store = SQLiteJobStore(database)
composition_job_store = SQLiteCompositionJobStore(database)
reconciliation_job_store = SQLiteReconciliationJobStore(database)
dag_repository = SQLiteDagRepository(database)
evidence_regeneration_service = EvidenceRegenerationService(repository, dag_repository, workspace)
job_executor: LocalJobExecutor | None = None
composition_job_executor: LocalCompositionJobExecutor | None = None
reconciliation_job_executor: LocalReconciliationJobExecutor | None = None
dag_executor: LocalDagExecutor | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global composition_job_executor, dag_executor, job_executor, reconciliation_job_executor
    database.initialize()
    job_executor = LocalJobExecutor(job_store, service.run_background)
    composition_job_executor = LocalCompositionJobExecutor(composition_job_store, service.run_composition_background)
    reconciliation_job_executor = LocalReconciliationJobExecutor(
        reconciliation_job_store, service.run_reconciliation_background
    )
    dag_executor = LocalDagExecutor(
        dag_repository,
        application_adapter_registry(service),
        settings.workspace,
    )
    try:
        yield
    finally:
        if job_executor is not None:
            job_executor.shutdown()
        if composition_job_executor is not None:
            composition_job_executor.shutdown()
        if reconciliation_job_executor is not None:
            reconciliation_job_executor.shutdown()
        if dag_executor is not None:
            dag_executor.shutdown()
        job_executor = None
        composition_job_executor = None
        reconciliation_job_executor = None
        dag_executor = None


app = FastAPI(
    title="DataPilot Studio Local API",
    version="0.1.0",
    description="Local-first dynamic data automation API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)


def get_service() -> DataPilotService:
    return service


def get_job_executor() -> LocalJobExecutor:
    if job_executor is None:
        raise HTTPException(503, "BACKGROUND_EXECUTOR_NOT_READY")
    return job_executor


def get_composition_job_executor() -> LocalCompositionJobExecutor:
    if composition_job_executor is None:
        raise HTTPException(503, "COMPOSITION_EXECUTOR_NOT_READY")
    return composition_job_executor


def get_reconciliation_job_executor() -> LocalReconciliationJobExecutor:
    if reconciliation_job_executor is None:
        raise HTTPException(503, "RECONCILIATION_EXECUTOR_NOT_READY")
    return reconciliation_job_executor


def get_dag_executor() -> LocalDagExecutor:
    if dag_executor is None:
        raise HTTPException(503, "DAG_EXECUTOR_NOT_READY")
    return dag_executor


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "local_only", "version": app.version}


@app.post("/api/v1/projects", response_model=Project, status_code=201)
def create_project(request: ProjectCreate, current: DataPilotService = Depends(get_service)) -> Project:
    return current.create_project(request)


@app.get("/api/v1/projects", response_model=list[Project])
def list_projects() -> list[Project]:
    return repository.list_projects()


@app.post("/api/v1/sources", response_model=SourceHandle, status_code=201)
def upload_source(
    project_id: UUID = Form(),
    file: UploadFile = File(),
    current: DataPilotService = Depends(get_service),
) -> SourceHandle:
    if not file.filename:
        raise HTTPException(400, "SOURCE_FILENAME_REQUIRED")
    try:
        return current.import_source(
            project_id,
            file.filename,
            file.content_type or "application/octet-stream",
            file.file,
        )
    except ValueError as error:
        raise HTTPException(415, str(error)) from error


@app.post("/api/v1/sources/{source_id}/discover", response_model=DiscoveryResult)
def discover(
    source_id: UUID,
    overrides: DiscoveryOverrides,
    current: DataPilotService = Depends(get_service),
) -> DiscoveryResult:
    try:
        return current.discover(source_id, overrides)
    except FileNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except (ValueError, OSError) as error:
        raise HTTPException(422, f"SOURCE_DISCOVERY_FAILED: {error}") from error


@app.post("/api/v1/mappings/validate", response_model=MappingSet)
def validate_mapping(mapping: MappingSet) -> MappingSet:
    return mapping


@app.post("/api/v1/schema-drift/analyze", response_model=SchemaDriftResult)
def analyze_drift(request: SchemaDriftRequest) -> SchemaDriftResult:
    return analyze_schema_drift(request.expectation, request.observed, request.policy)


@app.post("/api/v1/structures/compare", response_model=StructureComparisonResult)
def compare_dataset_structures(request: StructureComparisonRequest) -> StructureComparisonResult:
    return compare_structures(
        request.expectation,
        request.observed,
        request.policy,
        expected_key_unique=request.expected_key_unique,
        observed_key_unique=request.observed_key_unique,
    )


@app.post("/api/v1/mappings/repair", response_model=MappingRepairResponse)
def repair_drift_mapping(request: MappingRepairRequest) -> MappingRepairResponse:
    mapping, audit = repair_mapping(request.mapping, request.decisions)
    repository.save_mapping_decision(
        request.project_id,
        request.workflow_id,
        audit,
        request.run_id,
    )
    return MappingRepairResponse(mapping=mapping, audit=audit)


@app.post("/api/v1/batches/catalog", response_model=BatchCatalog)
def catalog_batch(request: BatchCatalogRequest, current: DataPilotService = Depends(get_service)) -> BatchCatalog:
    try:
        return current.batch_catalog(request)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/folders/scan", response_model=BatchCatalog)
def scan_local_folder(request: FolderScanRequest, current: DataPilotService = Depends(get_service)) -> BatchCatalog:
    try:
        return current.scan_folder(request)
    except (FileNotFoundError, ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/composition-plans", response_model=CompositionPlan, status_code=201)
def save_composition_plan(plan: CompositionPlan, current: DataPilotService = Depends(get_service)) -> CompositionPlan:
    try:
        return current.save_composition_plan(plan)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/projects/{project_id}/composition-plans", response_model=list[CompositionPlan])
def list_composition_plans(project_id: UUID) -> list[CompositionPlan]:
    return repository.list_composition_plans(project_id)


@app.post("/api/v1/compositions/preview", response_model=CompositionPreview)
def preview_composition(
    request: CompositionPreviewRequest, current: DataPilotService = Depends(get_service)
) -> CompositionPreview:
    try:
        return current.preview_composition(request)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/composition-jobs", response_model=BackgroundJobRecord, status_code=202)
def submit_composition_job(
    request: CompositionRunRequest,
    executor: LocalCompositionJobExecutor = Depends(get_composition_job_executor),
) -> BackgroundJobRecord:
    return executor.submit(CompositionJobSubmission(run=request))


@app.get("/api/v1/composition-jobs/{job_id}", response_model=BackgroundJobRecord)
def get_composition_job(job_id: UUID) -> BackgroundJobRecord:
    job = composition_job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return job


@app.get("/api/v1/composition-jobs/{job_id}/events", response_model=list[JobProgressEvent])
def get_composition_events(job_id: UUID) -> list[JobProgressEvent]:
    return composition_job_store.events(job_id)


@app.get("/api/v1/composition-jobs/{job_id}/checkpoints", response_model=list[CheckpointRecord])
def get_composition_checkpoints(job_id: UUID) -> list[CheckpointRecord]:
    return composition_job_store.checkpoints(job_id)


@app.post("/api/v1/composition-jobs/{job_id}/cancel", response_model=BackgroundJobRecord)
def cancel_composition_job(
    job_id: UUID,
    executor: LocalCompositionJobExecutor = Depends(get_composition_job_executor),
) -> BackgroundJobRecord:
    try:
        return executor.cancel(job_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error


@app.post("/api/v1/composition-jobs/{job_id}/retry", response_model=BackgroundJobRecord, status_code=202)
def retry_composition_job(
    job_id: UUID,
    executor: LocalCompositionJobExecutor = Depends(get_composition_job_executor),
) -> BackgroundJobRecord:
    try:
        return executor.retry(job_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/api/v1/batch-manifests/{run_id}", response_model=BatchManifest)
def get_batch_manifest(run_id: UUID) -> BatchManifest:
    manifest = repository.get_batch_manifest(run_id)
    if manifest is None:
        raise HTTPException(404, "BATCH_MANIFEST_NOT_FOUND")
    return manifest


@app.post("/api/v1/reconciliation-workflows", response_model=ReconciliationWorkflow, status_code=201)
def save_reconciliation_workflow(
    workflow: ReconciliationWorkflow,
    current: DataPilotService = Depends(get_service),
) -> ReconciliationWorkflow:
    try:
        return current.save_reconciliation_workflow(workflow)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get(
    "/api/v1/projects/{project_id}/reconciliation-workflows",
    response_model=list[ReconciliationWorkflow],
)
def list_reconciliation_workflows(project_id: UUID) -> list[ReconciliationWorkflow]:
    return repository.list_reconciliation_workflows(project_id)


@app.post("/api/v1/reconciliations/preview", response_model=ReconciliationResult)
def preview_reconciliation(
    request: ReconciliationPreviewRequest,
    current: DataPilotService = Depends(get_service),
) -> ReconciliationResult:
    try:
        return current.preview_reconciliation(request)
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/reconciliation-jobs", response_model=BackgroundJobRecord, status_code=202)
def submit_reconciliation_job(
    request: ReconciliationRunRequest,
    executor: LocalReconciliationJobExecutor = Depends(get_reconciliation_job_executor),
) -> BackgroundJobRecord:
    return executor.submit(ReconciliationJobSubmission(run=request))


@app.get("/api/v1/reconciliation-jobs/{job_id}", response_model=BackgroundJobRecord)
def get_reconciliation_job(job_id: UUID) -> BackgroundJobRecord:
    job = reconciliation_job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return job


@app.get("/api/v1/reconciliation-jobs/{job_id}/events", response_model=list[JobProgressEvent])
def get_reconciliation_events(job_id: UUID) -> list[JobProgressEvent]:
    return reconciliation_job_store.events(job_id)


@app.get("/api/v1/reconciliation-jobs/{job_id}/checkpoints", response_model=list[CheckpointRecord])
def get_reconciliation_checkpoints(job_id: UUID) -> list[CheckpointRecord]:
    return reconciliation_job_store.checkpoints(job_id)


@app.post("/api/v1/reconciliation-jobs/{job_id}/cancel", response_model=BackgroundJobRecord)
def cancel_reconciliation_job(
    job_id: UUID,
    executor: LocalReconciliationJobExecutor = Depends(get_reconciliation_job_executor),
) -> BackgroundJobRecord:
    try:
        return executor.cancel(job_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error


@app.post("/api/v1/reconciliation-jobs/{job_id}/retry", response_model=BackgroundJobRecord, status_code=202)
def retry_reconciliation_job(
    job_id: UUID,
    executor: LocalReconciliationJobExecutor = Depends(get_reconciliation_job_executor),
) -> BackgroundJobRecord:
    try:
        return executor.retry(job_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/api/v1/reconciliation-runs/{run_id}", response_model=ReconciliationRunRecord)
def get_reconciliation_run(run_id: UUID) -> ReconciliationRunRecord:
    record = repository.get_reconciliation_run(run_id)
    if record is None:
        raise HTTPException(404, "RECONCILIATION_RUN_NOT_FOUND")
    return record


@app.get("/api/v1/reconciliation-runs/{run_id}/reviews", response_model=list[ReviewQueueItem])
def list_reconciliation_reviews(run_id: UUID, status: str | None = None) -> list[ReviewQueueItem]:
    return repository.list_review_items(run_id, status)


@app.post("/api/v1/review-items/{review_item_id}/decisions", response_model=ReviewDecisionEvent, status_code=201)
def decide_review_item(review_item_id: UUID, event: ReviewDecisionEvent) -> ReviewDecisionEvent:
    if event.review_item_id != review_item_id:
        raise HTTPException(422, "REVIEW_ITEM_ID_MISMATCH")
    try:
        return repository.append_review_decision(event)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/review-items/{review_item_id}/decisions", response_model=list[ReviewDecisionEvent])
def list_review_decisions(review_item_id: UUID) -> list[ReviewDecisionEvent]:
    return repository.list_review_decisions(review_item_id)


@app.post("/api/v1/decision-memory", response_model=DecisionMemory, status_code=201)
def save_decision_memory(memory: DecisionMemory) -> DecisionMemory:
    return repository.save_decision_memory(memory)


@app.get("/api/v1/projects/{project_id}/decision-memory", response_model=list[DecisionMemory])
def list_decision_memory(project_id: UUID, active_only: bool = True) -> list[DecisionMemory]:
    return repository.list_decision_memory(project_id, active_only)


@app.get("/api/v1/projects/{project_id}/decision-memory/export", response_model=list[DecisionMemory])
def export_decision_memory(project_id: UUID, actor: str = "local-user") -> list[DecisionMemory]:
    return repository.export_decision_memory(project_id, actor)


@app.post("/api/v1/decision-memory/{memory_id}/deactivate", response_model=DecisionMemory)
def deactivate_decision_memory(memory_id: UUID, request: DecisionMemoryDeactivateRequest) -> DecisionMemory:
    try:
        return repository.deactivate_decision_memory(memory_id, request.actor, request.reason)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error


@app.get("/api/v1/reconciliation-manifests/{run_id}", response_model=ReconciliationExportManifest)
def get_reconciliation_manifest(run_id: UUID) -> ReconciliationExportManifest:
    manifest = repository.get_reconciliation_manifest(run_id)
    if manifest is None:
        raise HTTPException(404, "RECONCILIATION_MANIFEST_NOT_FOUND")
    return manifest


@app.post("/api/v1/workflows/validate", response_model=WorkflowConfiguration)
def validate_workflow(
    workflow: WorkflowConfiguration, current: DataPilotService = Depends(get_service)
) -> WorkflowConfiguration:
    try:
        return current.validate_workflow(workflow)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/workflows", response_model=WorkflowConfiguration, status_code=201)
def save_workflow(
    workflow: WorkflowConfiguration, current: DataPilotService = Depends(get_service)
) -> WorkflowConfiguration:
    try:
        return current.save_workflow(workflow)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/projects/{project_id}/workflows", response_model=list[WorkflowConfiguration])
def list_workflows(project_id: UUID) -> list[WorkflowConfiguration]:
    return repository.list_workflows(project_id)


@app.post("/api/v1/runs/preview", response_model=PreviewResult)
def preview(request: PreviewRequest, current: DataPilotService = Depends(get_service)) -> PreviewResult:
    try:
        return current.preview(request)
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/runs", response_model=RunRecord, status_code=201)
def run(request: RunRequest, current: DataPilotService = Depends(get_service)) -> RunRecord:
    try:
        return current.run(request)
    except FileNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except (ValueError, RuntimeError, OSError) as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/jobs", response_model=BackgroundJobRecord, status_code=202)
def submit_job(
    request: RunRequest,
    executor: LocalJobExecutor = Depends(get_job_executor),
) -> BackgroundJobRecord:
    return executor.submit(JobSubmission(run=request))


@app.get("/api/v1/jobs", response_model=list[BackgroundJobRecord])
def list_jobs(project_id: UUID | None = None) -> list[BackgroundJobRecord]:
    return job_store.list_jobs(project_id)


@app.get("/api/v1/jobs/{job_id}", response_model=BackgroundJobRecord)
def get_job(job_id: UUID) -> BackgroundJobRecord:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return job


@app.get("/api/v1/jobs/{job_id}/events", response_model=list[JobProgressEvent])
def get_job_events(job_id: UUID) -> list[JobProgressEvent]:
    if job_store.get(job_id) is None:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return job_store.events(job_id)


@app.get("/api/v1/jobs/{job_id}/checkpoints", response_model=list[CheckpointRecord])
def get_job_checkpoints(job_id: UUID) -> list[CheckpointRecord]:
    if job_store.get(job_id) is None:
        raise HTTPException(404, "JOB_NOT_FOUND")
    return job_store.checkpoints(job_id)


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=BackgroundJobRecord)
def cancel_job(
    job_id: UUID,
    executor: LocalJobExecutor = Depends(get_job_executor),
) -> BackgroundJobRecord:
    try:
        return executor.cancel(job_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error


@app.post("/api/v1/jobs/{job_id}/retry", response_model=BackgroundJobRecord, status_code=202)
def retry_job(
    job_id: UUID,
    executor: LocalJobExecutor = Depends(get_job_executor),
) -> BackgroundJobRecord:
    try:
        return executor.retry(job_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/api/v1/runs", response_model=list[RunRecord])
def list_runs(project_id: UUID | None = None) -> list[RunRecord]:
    return repository.list_runs(project_id)


@app.get("/api/v1/runs/{run_id}", response_model=RunRecord)
def get_run(run_id: UUID) -> RunRecord:
    record = repository.get_run(run_id)
    if record is None:
        raise HTTPException(404, "RUN_NOT_FOUND")
    return record


@app.get("/api/v1/artifacts/{run_id}/{artifact_index}", response_class=FileResponse)
def get_artifact(run_id: UUID, artifact_index: int) -> FileResponse:
    record = repository.get_run(run_id)
    if record is None or artifact_index < 0 or artifact_index >= len(record.artifacts):
        raise HTTPException(404, "ARTIFACT_NOT_FOUND")
    path = Path(record.artifacts[artifact_index]).resolve()
    runs_root = workspace.runs.resolve()
    if runs_root not in path.parents or not path.is_file():
        raise HTTPException(404, "ARTIFACT_NOT_FOUND")
    return FileResponse(path, filename=path.name)


@app.get("/api/v1/dag/capabilities", response_model=list[NodeCapability])
def list_dag_capabilities() -> list[NodeCapability]:
    return default_registry.list_capabilities()


@app.post("/api/v1/dag/validate", response_model=DagValidationResult)
def validate_dag_workflow(workflow: DagWorkflow) -> DagValidationResult:
    return validate_dag(workflow)


@app.post("/api/v1/dag/plan", response_model=ExecutionPlan)
def plan_dag_workflow(request: WorkflowPlanRequest) -> ExecutionPlan:
    try:
        return build_execution_plan(request.workflow, request.parameters)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/dag/diff", response_model=WorkflowDiff)
def diff_dag_workflow(request: WorkflowDiffRequest) -> WorkflowDiff:
    try:
        return diff_workflows(request.before, request.after)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/v1/dag/workflows", response_model=DagWorkflow, status_code=201)
def save_dag_workflow(workflow: DagWorkflow) -> DagWorkflow:
    validation = validate_dag(workflow)
    if workflow.lifecycle == WorkflowLifecycle.PUBLISHED and not validation.valid:
        raise HTTPException(422, "DAG_PUBLISH_VALIDATION_FAILED")
    try:
        return dag_repository.save_workflow(workflow)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.get("/api/v1/projects/{project_id}/dag-workflows", response_model=list[DagWorkflow])
def list_dag_workflows(project_id: UUID) -> list[DagWorkflow]:
    return dag_repository.list_workflows(project_id)


@app.get("/api/v1/dag/workflows/{workflow_id}", response_model=DagWorkflow)
def get_dag_workflow(workflow_id: UUID, version: int | None = None) -> DagWorkflow:
    workflow = dag_repository.get_workflow(workflow_id, version)
    if workflow is None:
        raise HTTPException(404, "DAG_WORKFLOW_NOT_FOUND")
    return workflow


@app.get("/api/v1/dag/workflows/{workflow_id}/history", response_model=list[DagWorkflow])
def get_dag_workflow_history(workflow_id: UUID) -> list[DagWorkflow]:
    latest = dag_repository.get_workflow(workflow_id)
    if latest is None:
        raise HTTPException(404, "DAG_WORKFLOW_NOT_FOUND")
    return [item for item in dag_repository.list_workflows(latest.project_id) if item.id == workflow_id]


@app.post("/api/v1/dag/workflows/{workflow_id}/versions", response_model=DagWorkflow, status_code=201)
def create_dag_workflow_version(workflow_id: UUID, request: WorkflowVersionRequest) -> DagWorkflow:
    latest = dag_repository.get_workflow(workflow_id)
    if latest is None:
        raise HTTPException(404, "DAG_WORKFLOW_NOT_FOUND")
    if request.workflow.id != workflow_id or request.workflow.project_id != latest.project_id:
        raise HTTPException(422, "DAG_WORKFLOW_IDENTITY_MISMATCH")
    now = datetime.now(UTC)
    created = request.workflow.model_copy(
        update={
            "version": latest.version + 1,
            "lifecycle": WorkflowLifecycle.DRAFT,
            "change_note": request.change_note,
            "created_at": now,
            "updated_at": now,
        }
    )
    return dag_repository.save_workflow(created)


@app.post("/api/v1/dag/workflows/{workflow_id}/publish", response_model=DagWorkflow)
def publish_dag_workflow(workflow_id: UUID, version: int) -> DagWorkflow:
    workflow = dag_repository.get_workflow(workflow_id, version)
    if workflow is None:
        raise HTTPException(404, "DAG_WORKFLOW_NOT_FOUND")
    validation = validate_dag(workflow)
    if not validation.valid:
        raise HTTPException(422, "DAG_PUBLISH_VALIDATION_FAILED")
    published = workflow.model_copy(update={"lifecycle": WorkflowLifecycle.PUBLISHED, "updated_at": datetime.now(UTC)})
    return dag_repository.save_workflow(published)


@app.post("/api/v1/dag/workflows/{workflow_id}/clone", response_model=DagWorkflow, status_code=201)
def clone_dag_workflow(workflow_id: UUID, request: WorkflowCloneRequest) -> DagWorkflow:
    source = dag_repository.get_workflow(workflow_id)
    if source is None:
        raise HTTPException(404, "DAG_WORKFLOW_NOT_FOUND")
    now = datetime.now(UTC)
    clone = source.model_copy(
        update={
            "id": uuid4(),
            "version": 1,
            "display_name": request.display_name,
            "owner_reference": request.owner_reference,
            "lifecycle": WorkflowLifecycle.DRAFT,
            "change_note": f"Cloned from {source.id} version {source.version}",
            "created_at": now,
            "updated_at": now,
        }
    )
    return dag_repository.save_workflow(clone)


@app.post("/api/v1/dag/workflows/{workflow_id}/restore", response_model=DagWorkflow, status_code=201)
def restore_dag_workflow(workflow_id: UUID, request: WorkflowRestoreRequest) -> DagWorkflow:
    source = dag_repository.get_workflow(workflow_id, request.source_version)
    latest = dag_repository.get_workflow(workflow_id)
    if source is None or latest is None:
        raise HTTPException(404, "DAG_WORKFLOW_VERSION_NOT_FOUND")
    now = datetime.now(UTC)
    restored = source.model_copy(
        update={
            "version": latest.version + 1,
            "lifecycle": WorkflowLifecycle.DRAFT,
            "change_note": request.change_note,
            "created_at": now,
            "updated_at": now,
        }
    )
    return dag_repository.save_workflow(restored)


@app.post("/api/v1/dag/runs", response_model=DagRunRecord, status_code=202)
def submit_dag_run(
    request: DagRunRequest,
    executor: LocalDagExecutor = Depends(get_dag_executor),
) -> DagRunRecord:
    try:
        return executor.submit(DagJobSubmission(request=request))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/dag/runs", response_model=list[DagRunRecord])
def list_dag_runs(project_id: UUID | None = None) -> list[DagRunRecord]:
    return dag_repository.list_runs(project_id)


@app.get("/api/v1/dag/runs/{run_id}", response_model=DagRunRecord)
def get_dag_run(run_id: UUID) -> DagRunRecord:
    run = dag_repository.get_run(run_id)
    if run is None:
        raise HTTPException(404, "DAG_RUN_NOT_FOUND")
    return run


@app.get("/api/v1/dag/runs/{run_id}/nodes", response_model=list[NodeRunRecord])
def list_dag_node_runs(run_id: UUID) -> list[NodeRunRecord]:
    if dag_repository.get_run(run_id) is None:
        raise HTTPException(404, "DAG_RUN_NOT_FOUND")
    return dag_repository.list_node_runs(run_id)


@app.get("/api/v1/dag/runs/{run_id}/checkpoints", response_model=list[ManualCheckpoint])
def list_dag_checkpoints(run_id: UUID) -> list[ManualCheckpoint]:
    if dag_repository.get_run(run_id) is None:
        raise HTTPException(404, "DAG_RUN_NOT_FOUND")
    return dag_repository.list_checkpoints(run_id)


@app.post("/api/v1/dag/runs/{run_id}/cancel", response_model=DagRunRecord)
def cancel_dag_run(run_id: UUID, executor: LocalDagExecutor = Depends(get_dag_executor)) -> DagRunRecord:
    try:
        return executor.cancel(run_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error


@app.post("/api/v1/dag/runs/{run_id}/resume", response_model=DagRunRecord, status_code=202)
def resume_dag_run(run_id: UUID, executor: LocalDagExecutor = Depends(get_dag_executor)) -> DagRunRecord:
    try:
        return executor.resume(run_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/api/v1/dag/runs/{run_id}/retry", response_model=DagRunRecord, status_code=202)
def retry_dag_run(run_id: UUID, executor: LocalDagExecutor = Depends(get_dag_executor)) -> DagRunRecord:
    try:
        return executor.retry(run_id)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@app.post(
    "/api/v1/dag/checkpoints/{checkpoint_id}/decisions",
    response_model=ManualCheckpointDecision,
    status_code=201,
)
def decide_dag_checkpoint(checkpoint_id: UUID, decision: ManualCheckpointDecision) -> ManualCheckpointDecision:
    if decision.checkpoint_id != checkpoint_id:
        raise HTTPException(422, "DAG_CHECKPOINT_ID_MISMATCH")
    try:
        return dag_repository.append_decision(decision)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get(
    "/api/v1/dag/checkpoints/{checkpoint_id}/decisions",
    response_model=list[ManualCheckpointDecision],
)
def list_dag_checkpoint_decisions(checkpoint_id: UUID) -> list[ManualCheckpointDecision]:
    if dag_repository.get_checkpoint(checkpoint_id) is None:
        raise HTTPException(404, "DAG_CHECKPOINT_NOT_FOUND")
    return dag_repository.list_decisions(checkpoint_id)


@app.post(
    "/api/v1/reconciliation-runs/{run_id}/evidence-versions",
    response_model=EvidencePackageVersion,
    status_code=201,
)
def regenerate_reconciliation_evidence(run_id: UUID, request: EvidenceRegenerationRequest) -> EvidencePackageVersion:
    if request.run_id != run_id:
        raise HTTPException(422, "RECONCILIATION_RUN_ID_MISMATCH")
    try:
        return evidence_regeneration_service.regenerate(request)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error
    except (ValueError, FileNotFoundError, FileExistsError) as error:
        raise HTTPException(422, str(error)) from error


@app.get(
    "/api/v1/reconciliation-runs/{run_id}/evidence-versions",
    response_model=list[EvidencePackageVersion],
)
def list_reconciliation_evidence_versions(run_id: UUID) -> list[EvidencePackageVersion]:
    return dag_repository.list_evidence_versions(run_id)


@app.post("/api/v1/dag/subflows", response_model=SubflowDefinition, status_code=201)
def save_dag_subflow(subflow: SubflowDefinition) -> SubflowDefinition:
    try:
        return dag_repository.save_subflow(subflow)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/api/v1/projects/{project_id}/dag-subflows", response_model=list[SubflowDefinition])
def list_dag_subflows(project_id: UUID) -> list[SubflowDefinition]:
    return dag_repository.list_subflows(project_id)


@app.get("/api/v1/dag/subflows/{subflow_id}/versions/{version}", response_model=SubflowDefinition)
def get_dag_subflow(subflow_id: UUID, version: int) -> SubflowDefinition:
    subflow = dag_repository.get_subflow(subflow_id, version)
    if subflow is None:
        raise HTTPException(404, "DAG_SUBFLOW_VERSION_NOT_FOUND")
    return subflow
