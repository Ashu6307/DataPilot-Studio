"""Application services coordinating repositories and the generic engine."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from packages.contracts import (
    DiscoveryOverrides,
    DiscoveryResult,
    PreviewRequest,
    PreviewResult,
    Project,
    ProjectCreate,
    RunRecord,
    RunRequest,
    SourceHandle,
    WorkflowConfiguration,
)
from packages.data_engine import EngineRuntime, RuntimeExecutionError, SourceFile, Workspace, discover_source
from packages.workflow_schema import assert_secret_free

from .repositories import MetadataRepository


class DataPilotService:
    def __init__(self, repository: MetadataRepository, workspace: Workspace) -> None:
        self.repository = repository
        self.workspace = workspace
        self.runtime = EngineRuntime(workspace)

    def create_project(self, request: ProjectCreate) -> Project:
        return self.repository.create_project(Project(**request.model_dump()))

    def import_source(
        self, project_id: UUID, filename: str, media_type: str, stream: BinaryIO
    ) -> SourceHandle:
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
