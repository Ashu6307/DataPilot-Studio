"""Repository interfaces and SQLite implementations."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from packages.contracts import (
    BatchCatalog,
    BatchManifest,
    CompositionPlan,
    DecisionMemory,
    DecisionMemoryAuditEvent,
    MappingDecisionAudit,
    Project,
    ReconciliationExportManifest,
    ReconciliationRunRecord,
    ReconciliationWorkflow,
    ReviewDecisionEvent,
    ReviewQueueItem,
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
    def save_reconciliation_workflow(self, workflow: ReconciliationWorkflow) -> ReconciliationWorkflow: ...
    def list_reconciliation_workflows(self, project_id: UUID) -> list[ReconciliationWorkflow]: ...
    def save_reconciliation_run(self, run: ReconciliationRunRecord) -> ReconciliationRunRecord: ...
    def get_reconciliation_run(self, run_id: UUID) -> ReconciliationRunRecord | None: ...
    def save_review_items(self, items: list[ReviewQueueItem]) -> list[ReviewQueueItem]: ...
    def list_review_items(self, run_id: UUID, status: str | None = None) -> list[ReviewQueueItem]: ...
    def append_review_decision(self, event: ReviewDecisionEvent) -> ReviewDecisionEvent: ...
    def list_review_decisions(self, review_item_id: UUID) -> list[ReviewDecisionEvent]: ...
    def save_decision_memory(self, memory: DecisionMemory) -> DecisionMemory: ...
    def list_decision_memory(self, project_id: UUID, active_only: bool = True) -> list[DecisionMemory]: ...
    def deactivate_decision_memory(self, memory_id: UUID, actor: str, reason: str) -> DecisionMemory: ...
    def export_decision_memory(self, project_id: UUID, actor: str) -> list[DecisionMemory]: ...
    def save_reconciliation_manifest(
        self, manifest: ReconciliationExportManifest
    ) -> ReconciliationExportManifest: ...
    def get_reconciliation_manifest(self, run_id: UUID) -> ReconciliationExportManifest | None: ...


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

    def save_reconciliation_workflow(self, workflow: ReconciliationWorkflow) -> ReconciliationWorkflow:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO reconciliation_workflows VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(workflow.id),
                    workflow.version,
                    str(workflow.project_id),
                    workflow.display_name,
                    workflow.model_dump_json(),
                    workflow.created_at.isoformat(),
                ),
            )
        return workflow

    def list_reconciliation_workflows(self, project_id: UUID) -> list[ReconciliationWorkflow]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT configuration_json FROM reconciliation_workflows "
                "WHERE project_id = ? ORDER BY created_at DESC",
                (str(project_id),),
            ).fetchall()
        return [ReconciliationWorkflow.model_validate_json(row["configuration_json"]) for row in rows]

    def save_reconciliation_run(self, run: ReconciliationRunRecord) -> ReconciliationRunRecord:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO reconciliation_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(run.run_id),
                    str(run.project_id),
                    str(run.workflow_id),
                    run.workflow_version,
                    run.status,
                    run.summary.model_dump_json(),
                    json.dumps(run.audit),
                    run.created_at.isoformat(),
                ),
            )
        return run

    def get_reconciliation_run(self, run_id: UUID) -> ReconciliationRunRecord | None:
        from packages.contracts import ReconciliationSummary

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM reconciliation_runs WHERE run_id = ?", (str(run_id),)
            ).fetchone()
        if row is None:
            return None
        return ReconciliationRunRecord(
            run_id=row["run_id"],
            project_id=row["project_id"],
            workflow_id=row["workflow_id"],
            workflow_version=row["workflow_version"],
            status=row["status"],
            summary=ReconciliationSummary.model_validate_json(row["summary_json"]),
            audit=json.loads(row["audit_json"]),
            created_at=row["created_at"],
        )

    def save_review_items(self, items: list[ReviewQueueItem]) -> list[ReviewQueueItem]:
        with self.database.connect() as connection:
            for item in items:
                connection.execute(
                    "INSERT INTO review_items VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        str(item.id),
                        str(item.reconciliation_run_id),
                        item.status,
                        item.model_dump_json(),
                        item.created_at.isoformat(),
                        item.created_at.isoformat(),
                    ),
                )
        return items

    def list_review_items(self, run_id: UUID, status: str | None = None) -> list[ReviewQueueItem]:
        query = "SELECT item_json FROM review_items WHERE run_id = ?"
        parameters: tuple[str, ...] = (str(run_id),)
        if status is not None:
            query += " AND status = ?"
            parameters = (str(run_id), status)
        query += " ORDER BY created_at"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [ReviewQueueItem.model_validate_json(row["item_json"]) for row in rows]

    def append_review_decision(self, event: ReviewDecisionEvent) -> ReviewDecisionEvent:
        from datetime import UTC, datetime

        from packages.contracts import ReviewStatus

        with self.database.connect() as connection:
            item_row = connection.execute(
                "SELECT item_json FROM review_items WHERE id = ?", (str(event.review_item_id),)
            ).fetchone()
            if item_row is None:
                raise KeyError("REVIEW_ITEM_NOT_FOUND")
            if event.supersedes_event_id is not None:
                previous = connection.execute(
                    "SELECT review_item_id FROM review_decision_events WHERE id = ?",
                    (str(event.supersedes_event_id),),
                ).fetchone()
                if previous is None or previous["review_item_id"] != str(event.review_item_id):
                    raise ValueError("REVIEW_SUPERSEDED_EVENT_INVALID")
            item = ReviewQueueItem.model_validate_json(item_row["item_json"])
            existing_count = connection.execute(
                "SELECT COUNT(*) FROM review_decision_events WHERE review_item_id = ?",
                (str(event.review_item_id),),
            ).fetchone()[0]
            if existing_count and event.supersedes_event_id is None:
                raise ValueError("REVIEW_DECISION_EDIT_REQUIRES_SUPERSEDES_EVENT")
            if event.supersedes_event_id is not None:
                superseded_count = connection.execute(
                    "SELECT COUNT(*) FROM review_decision_events WHERE supersedes_event_id = ?",
                    (str(event.supersedes_event_id),),
                ).fetchone()[0]
                if superseded_count:
                    raise ValueError("REVIEW_DECISION_EVENT_ALREADY_SUPERSEDED")
            candidate_ids = {candidate.right.record_id for candidate in item.candidates}
            if event.decision.value == "approve_alternate_candidate" and not event.selected_candidate_record_id:
                raise ValueError("REVIEW_ALTERNATE_CANDIDATE_REQUIRED")
            if event.selected_candidate_record_id and event.selected_candidate_record_id not in candidate_ids:
                raise ValueError("REVIEW_SELECTED_CANDIDATE_INVALID")
            status = {
                "approve_suggested_match": ReviewStatus.APPROVED,
                "approve_alternate_candidate": ReviewStatus.APPROVED,
                "reject_all_candidates": ReviewStatus.REJECTED,
                "mark_duplicate": ReviewStatus.REJECTED,
                "defer": ReviewStatus.DEFERRED,
                "escalate": ReviewStatus.ESCALATED,
            }[event.decision.value]
            updated = item.model_copy(
                update={
                    "status": status,
                    "reviewer": event.reviewer,
                    "decision_timestamp": event.created_at,
                    "comment": event.comment,
                    "audit_event_ids": [*item.audit_event_ids, event.id],
                }
            )
            connection.execute(
                "INSERT INTO review_decision_events VALUES (?, ?, ?, ?, ?)",
                (
                    str(event.id),
                    str(event.review_item_id),
                    str(event.supersedes_event_id) if event.supersedes_event_id else None,
                    event.model_dump_json(),
                    event.created_at.isoformat(),
                ),
            )
            connection.execute(
                "UPDATE review_items SET status = ?, item_json = ?, updated_at = ? WHERE id = ?",
                (status, updated.model_dump_json(), datetime.now(UTC).isoformat(), str(item.id)),
            )
        return event

    def list_review_decisions(self, review_item_id: UUID) -> list[ReviewDecisionEvent]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM review_decision_events "
                "WHERE review_item_id = ? ORDER BY created_at",
                (str(review_item_id),),
            ).fetchall()
        return [ReviewDecisionEvent.model_validate_json(row["event_json"]) for row in rows]

    def save_decision_memory(self, memory: DecisionMemory) -> DecisionMemory:
        event = DecisionMemoryAuditEvent(memory_id=memory.id, action="created", actor=memory.created_by)
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO decision_memory VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(memory.id),
                    str(memory.project_id),
                    memory.kind,
                    int(memory.active),
                    memory.model_dump_json(),
                    memory.created_at.isoformat(),
                    memory.created_at.isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO decision_memory_events VALUES (?, ?, ?, ?, ?)",
                (str(event.id), str(memory.id), event.action, event.model_dump_json(), event.created_at.isoformat()),
            )
        return memory

    def list_decision_memory(self, project_id: UUID, active_only: bool = True) -> list[DecisionMemory]:
        query = "SELECT memory_json FROM decision_memory WHERE project_id = ?"
        parameters: tuple[str, ...] = (str(project_id),)
        if active_only:
            query += " AND active = 1"
        query += " ORDER BY created_at"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [DecisionMemory.model_validate_json(row["memory_json"]) for row in rows]

    def deactivate_decision_memory(self, memory_id: UUID, actor: str, reason: str) -> DecisionMemory:
        from datetime import UTC, datetime

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT memory_json FROM decision_memory WHERE id = ?", (str(memory_id),)
            ).fetchone()
            if row is None:
                raise KeyError("DECISION_MEMORY_NOT_FOUND")
            memory = DecisionMemory.model_validate_json(row["memory_json"])
            deactivated = memory.model_copy(
                update={
                    "source_value": "[deleted]",
                    "canonical_value": "[deleted]",
                    "expires_at": None,
                    "confidence": Decimal(0),
                    "active": False,
                    "created_by": "[deleted]",
                }
            )
            event = DecisionMemoryAuditEvent(
                memory_id=memory_id,
                action="deactivated",
                actor=actor,
                reason=reason,
            )
            connection.execute(
                "UPDATE decision_memory SET active = 0, memory_json = ?, updated_at = ? WHERE id = ?",
                (deactivated.model_dump_json(), datetime.now(UTC).isoformat(), str(memory_id)),
            )
            connection.execute(
                "INSERT INTO decision_memory_events VALUES (?, ?, ?, ?, ?)",
                (str(event.id), str(memory_id), event.action, event.model_dump_json(), event.created_at.isoformat()),
            )
        return deactivated

    def export_decision_memory(self, project_id: UUID, actor: str) -> list[DecisionMemory]:
        memories = self.list_decision_memory(project_id, active_only=False)
        with self.database.connect() as connection:
            for memory in memories:
                event = DecisionMemoryAuditEvent(memory_id=memory.id, action="exported", actor=actor)
                connection.execute(
                    "INSERT INTO decision_memory_events VALUES (?, ?, ?, ?, ?)",
                    (
                        str(event.id),
                        str(memory.id),
                        event.action,
                        event.model_dump_json(),
                        event.created_at.isoformat(),
                    ),
                )
        return memories

    def save_reconciliation_manifest(
        self, manifest: ReconciliationExportManifest
    ) -> ReconciliationExportManifest:
        with self.database.connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO reconciliation_export_manifests VALUES (?, ?, ?)",
                (str(manifest.run_id), manifest.model_dump_json(), manifest.created_at.isoformat()),
            )
        return manifest

    def get_reconciliation_manifest(self, run_id: UUID) -> ReconciliationExportManifest | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT manifest_json FROM reconciliation_export_manifests WHERE run_id = ?",
                (str(run_id),),
            ).fetchone()
        return ReconciliationExportManifest.model_validate_json(row["manifest_json"]) if row else None
