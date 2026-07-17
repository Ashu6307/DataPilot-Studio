"""Repository interfaces and SQLite implementations."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from packages.contracts import (
    BatchCatalog,
    BatchManifest,
    CompositionPlan,
    MappingDecisionAudit,
    Project,
    RunRecord,
    SourceHandle,
    WorkflowConfiguration,
)

from .database import Database


class MetadataRepository(Protocol):
    def create_project(self, project: Project) -> Project: ...
    def list_projects(self) -> list[Project]: ...
    def save_source(self, source: SourceHandle) -> SourceHandle: ...
    def get_source(self, source_id: UUID) -> SourceHandle | None: ...
    def save_workflow(self, workflow: WorkflowConfiguration) -> WorkflowConfiguration: ...
    def list_workflows(self, project_id: UUID) -> list[WorkflowConfiguration]: ...
    def save_run(self, run: RunRecord) -> RunRecord: ...
    def get_run(self, run_id: UUID) -> RunRecord | None: ...
    def list_runs(self, project_id: UUID | None = None) -> list[RunRecord]: ...
    def save_mapping_decision(
        self,
        project_id: UUID,
        workflow_id: UUID,
        audit: MappingDecisionAudit,
        run_id: UUID | None = None,
    ) -> MappingDecisionAudit: ...
    def save_composition_plan(self, plan: CompositionPlan) -> CompositionPlan: ...
    def list_composition_plans(self, project_id: UUID) -> list[CompositionPlan]: ...
    def save_batch_manifest(self, project_id: UUID, manifest: BatchManifest) -> BatchManifest: ...
    def get_batch_manifest(self, run_id: UUID) -> BatchManifest | None: ...
    def save_folder_catalog(self, catalog: BatchCatalog, configuration_json: str) -> BatchCatalog: ...


class SQLiteMetadataRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_project(self, project: Project) -> Project:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(project.id),
                    project.name,
                    project.locale,
                    project.privacy_mode,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
        return project

    def list_projects(self) -> list[Project]:
        with self.database.connect() as connection:
            rows = connection.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return [Project.model_validate(dict(row)) for row in rows]

    def save_source(self, source: SourceHandle) -> SourceHandle:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(source.id),
                    str(source.project_id),
                    source.original_filename,
                    source.media_type,
                    source.size_bytes,
                    source.sha256,
                    source.created_at.isoformat(),
                ),
            )
        return source

    def get_source(self, source_id: UUID) -> SourceHandle | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM sources WHERE id = ?", (str(source_id),)).fetchone()
        return SourceHandle.model_validate(dict(row)) if row else None

    def save_workflow(self, workflow: WorkflowConfiguration) -> WorkflowConfiguration:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO workflows VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(workflow.id),
                    workflow.workflow_version,
                    str(workflow.project_id),
                    workflow.display_name,
                    workflow.model_dump_json(),
                    workflow.created_at.isoformat(),
                ),
            )
        return workflow

    def list_workflows(self, project_id: UUID) -> list[WorkflowConfiguration]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT configuration_json FROM workflows WHERE project_id = ? ORDER BY created_at DESC",
                (str(project_id),),
            ).fetchall()
        return [WorkflowConfiguration.model_validate_json(row["configuration_json"]) for row in rows]

    def save_run(self, run: RunRecord) -> RunRecord:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(run.id),
                    str(run.project_id),
                    str(run.workflow_id),
                    run.workflow_version,
                    run.status,
                    run.model_dump_json(),
                    run.started_at.isoformat(),
                ),
            )
        return run

    def get_run(self, run_id: UUID) -> RunRecord | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT record_json FROM runs WHERE id = ?", (str(run_id),)).fetchone()
        return RunRecord.model_validate_json(row["record_json"]) if row else None

    def list_runs(self, project_id: UUID | None = None) -> list[RunRecord]:
        query = "SELECT record_json FROM runs"
        params: tuple[str, ...] = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            params = (str(project_id),)
        query += " ORDER BY created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [RunRecord.model_validate_json(row["record_json"]) for row in rows]

    def save_mapping_decision(
        self,
        project_id: UUID,
        workflow_id: UUID,
        audit: MappingDecisionAudit,
        run_id: UUID | None = None,
    ) -> MappingDecisionAudit:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO mapping_decisions
                (project_id, workflow_id, run_id, audit_json, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    str(project_id),
                    str(workflow_id),
                    str(run_id) if run_id else None,
                    audit.model_dump_json(),
                    audit.created_at.isoformat(),
                ),
            )
        return audit

    def save_composition_plan(self, plan: CompositionPlan) -> CompositionPlan:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO composition_plans VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(plan.id),
                    plan.version,
                    str(plan.project_id),
                    plan.display_name,
                    plan.model_dump_json(),
                    plan.created_at.isoformat(),
                ),
            )
            for source in plan.alignment.sources:
                connection.execute(
                    """INSERT INTO alignment_decisions
                    (plan_id, plan_version, source_id, decision_json, created_at)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        str(plan.id),
                        plan.version,
                        str(source.source_id),
                        source.model_dump_json(),
                        plan.updated_at.isoformat(),
                    ),
                )
        return plan

    def list_composition_plans(self, project_id: UUID) -> list[CompositionPlan]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT configuration_json FROM composition_plans WHERE project_id = ? ORDER BY created_at DESC",
                (str(project_id),),
            ).fetchall()
        return [CompositionPlan.model_validate_json(row["configuration_json"]) for row in rows]

    def save_batch_manifest(self, project_id: UUID, manifest: BatchManifest) -> BatchManifest:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO batch_manifests VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(manifest.run_id),
                    str(project_id),
                    str(manifest.plan_id),
                    manifest.plan_version,
                    manifest.model_dump_json(),
                    manifest.created_at.isoformat(),
                ),
            )
        return manifest

    def get_batch_manifest(self, run_id: UUID) -> BatchManifest | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM batch_manifests WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        return BatchManifest.model_validate_json(row["manifest_json"]) if row else None

    def save_folder_catalog(self, catalog: BatchCatalog, configuration_json: str) -> BatchCatalog:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO folder_scan_history VALUES (?, ?, ?, ?, ?)",
                (
                    str(catalog.id),
                    str(catalog.project_id),
                    configuration_json,
                    catalog.model_dump_json(),
                    catalog.created_at.isoformat(),
                ),
            )
        return catalog
