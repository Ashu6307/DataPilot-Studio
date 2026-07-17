"""FastAPI entrypoint for the local DataPilot service."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from packages.contracts import (
    BackgroundJobRecord,
    CheckpointRecord,
    DiscoveryOverrides,
    DiscoveryResult,
    JobProgressEvent,
    JobSubmission,
    MappingRepairRequest,
    MappingRepairResponse,
    MappingSet,
    PreviewRequest,
    PreviewResult,
    Project,
    ProjectCreate,
    RunRecord,
    RunRequest,
    SchemaDriftRequest,
    SchemaDriftResult,
    SourceHandle,
    WorkflowConfiguration,
)
from packages.data_engine import LocalJobExecutor, Workspace
from packages.data_engine.schema_drift import analyze_schema_drift, repair_mapping

from .config import load_settings
from .database import Database
from .job_store import SQLiteJobStore
from .repositories import SQLiteMetadataRepository
from .services import DataPilotService

settings = load_settings()
database = Database(settings.database)
repository = SQLiteMetadataRepository(database)
workspace = Workspace(settings.workspace)
service = DataPilotService(repository, workspace)
job_store = SQLiteJobStore(database)
job_executor: LocalJobExecutor | None = None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    global job_executor
    database.initialize()
    job_executor = LocalJobExecutor(job_store, service.run_background)
    try:
        yield
    finally:
        if job_executor is not None:
            job_executor.shutdown()
        job_executor = None


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
