"""SQLite metadata persistence for versioned DAG workflows and executions."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from packages.contracts import (
    ArtifactReference,
    DagRunRecord,
    DagRunRequest,
    DagRunStatus,
    DagWorkflow,
    EvidencePackageVersion,
    ExecutionPlan,
    ManualCheckpoint,
    ManualCheckpointDecision,
    NodeRunRecord,
    SubflowDefinition,
)

from .database import Database


class SQLiteDagRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save_workflow(self, workflow: DagWorkflow) -> DagWorkflow:
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT definition_json FROM dag_workflows WHERE id = ? AND version = ?",
                (str(workflow.id), workflow.version),
            ).fetchone()
            if existing:
                stored = DagWorkflow.model_validate_json(existing["definition_json"])
                if stored.lifecycle.value == "published" and stored != workflow:
                    raise ValueError("DAG_PUBLISHED_VERSION_IMMUTABLE")
                connection.execute(
                    """UPDATE dag_workflows SET display_name = ?, lifecycle = ?, definition_json = ?,
                    updated_at = ? WHERE id = ? AND version = ?""",
                    (
                        workflow.display_name,
                        workflow.lifecycle,
                        workflow.model_dump_json(),
                        workflow.updated_at.isoformat(),
                        str(workflow.id),
                        workflow.version,
                    ),
                )
            else:
                connection.execute(
                    """INSERT INTO dag_workflows
                    (id, version, project_id, display_name, lifecycle, definition_json,
                     parent_version, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(workflow.id),
                        workflow.version,
                        str(workflow.project_id),
                        workflow.display_name,
                        workflow.lifecycle,
                        workflow.model_dump_json(),
                        workflow.version - 1 if workflow.version > 1 else None,
                        workflow.created_at.isoformat(),
                        workflow.updated_at.isoformat(),
                    ),
                )
        return workflow

    def get_workflow(self, workflow_id: UUID, version: int | None = None) -> DagWorkflow | None:
        query = "SELECT definition_json FROM dag_workflows WHERE id = ?"
        parameters: tuple[str | int, ...] = (str(workflow_id),)
        if version is not None:
            query += " AND version = ?"
            parameters += (version,)
        query += " ORDER BY version DESC LIMIT 1"
        with self.database.connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return DagWorkflow.model_validate_json(row["definition_json"]) if row else None

    def list_workflows(self, project_id: UUID) -> list[DagWorkflow]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT definition_json FROM dag_workflows WHERE project_id = ?
                ORDER BY updated_at DESC, version DESC""",
                (str(project_id),),
            ).fetchall()
        return [DagWorkflow.model_validate_json(row["definition_json"]) for row in rows]

    def save_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO dag_execution_plans
                (id, workflow_id, workflow_version, plan_fingerprint, parameter_fingerprint,
                 plan_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(plan.id),
                    str(plan.workflow_id),
                    plan.workflow_version,
                    plan.plan_fingerprint,
                    plan.parameter_fingerprint,
                    plan.model_dump_json(),
                    plan.created_at.isoformat(),
                ),
            )
        return plan

    def get_plan(self, plan_id: UUID) -> ExecutionPlan | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT plan_json FROM dag_execution_plans WHERE id = ?", (str(plan_id),)
            ).fetchone()
        return ExecutionPlan.model_validate_json(row["plan_json"]) if row else None

    def create_run(self, run: DagRunRecord, request: DagRunRequest) -> DagRunRecord:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO dag_runs
                (id, project_id, workflow_id, workflow_version, plan_id, status, request_json,
                 record_json, started_at, completed_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(run.id),
                    str(run.project_id),
                    str(run.workflow_id),
                    run.workflow_version,
                    str(run.plan_id),
                    run.status,
                    request.model_dump_json(),
                    run.model_dump_json(),
                    run.started_at.isoformat() if run.started_at else None,
                    run.completed_at.isoformat() if run.completed_at else None,
                    run.created_at.isoformat(),
                ),
            )
        return run

    def get_request(self, run_id: UUID) -> DagRunRequest | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT request_json FROM dag_runs WHERE id = ?", (str(run_id),)).fetchone()
        return DagRunRequest.model_validate_json(row["request_json"]) if row else None

    def get_run(self, run_id: UUID) -> DagRunRecord | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT record_json FROM dag_runs WHERE id = ?", (str(run_id),)).fetchone()
        return DagRunRecord.model_validate_json(row["record_json"]) if row else None

    def update_run(self, run: DagRunRecord) -> DagRunRecord:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """UPDATE dag_runs SET status = ?, record_json = ?, started_at = ?, completed_at = ?
                WHERE id = ?""",
                (
                    run.status,
                    run.model_dump_json(),
                    run.started_at.isoformat() if run.started_at else None,
                    run.completed_at.isoformat() if run.completed_at else None,
                    str(run.id),
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError("DAG_RUN_NOT_FOUND")
        return run

    def list_runs(self, project_id: UUID | None = None) -> list[DagRunRecord]:
        query = "SELECT record_json FROM dag_runs"
        parameters: tuple[str, ...] = ()
        if project_id is not None:
            query += " WHERE project_id = ?"
            parameters = (str(project_id),)
        query += " ORDER BY created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [DagRunRecord.model_validate_json(row["record_json"]) for row in rows]

    def recover_orphans(self) -> list[DagRunRecord]:
        recoverable = {"planning", "validating", "running", "cancelling"}
        recovered: list[DagRunRecord] = []
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM dag_runs WHERE status IN (?, ?, ?, ?)", tuple(sorted(recoverable))
            ).fetchall()
            for row in rows:
                run = DagRunRecord.model_validate_json(row["record_json"])
                changed = run.model_copy(
                    update={
                        "status": DagRunStatus.RECOVERY_REQUIRED,
                        "output_available": False,
                        "error_code": "DAG_PROCESS_INTERRUPTED",
                        "error_message": "The local process stopped before the run reached a terminal state.",
                        "updated_at": datetime.now(UTC),
                    }
                )
                connection.execute(
                    "UPDATE dag_runs SET status = ?, record_json = ? WHERE id = ?",
                    (changed.status, changed.model_dump_json(), str(changed.id)),
                )
                recovered.append(changed)
        return recovered

    def save_node_run(self, record: NodeRunRecord) -> NodeRunRecord:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO dag_node_runs
                (id, run_id, node_id, attempt, status, record_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, node_id, attempt) DO UPDATE SET
                status = excluded.status, record_json = excluded.record_json, updated_at = excluded.updated_at""",
                (
                    str(record.id),
                    str(record.run_id),
                    record.node_id,
                    record.attempt,
                    record.status,
                    record.model_dump_json(),
                    (record.started_at or record.updated_at).isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        return record

    def list_node_runs(self, run_id: UUID) -> list[NodeRunRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM dag_node_runs WHERE run_id = ? ORDER BY created_at, node_id",
                (str(run_id),),
            ).fetchall()
        return [NodeRunRecord.model_validate_json(row["record_json"]) for row in rows]

    def save_artifacts(self, run_id: UUID, artifacts: Iterable[ArtifactReference]) -> None:
        with self.database.connect() as connection:
            for artifact in artifacts:
                connection.execute(
                    """INSERT OR REPLACE INTO dag_artifacts
                    (id, run_id, producer_node_id, artifact_type, sha256, path_reference,
                     metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(artifact.artifact_id),
                        str(run_id),
                        artifact.producer_node_id,
                        artifact.artifact_type,
                        artifact.sha256,
                        artifact.path_reference,
                        artifact.model_dump_json(include={"row_count", "metadata"}),
                        datetime.now(UTC).isoformat(),
                    ),
                )

    def save_checkpoint(self, checkpoint: ManualCheckpoint) -> ManualCheckpoint:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO dag_manual_checkpoints
                (id, run_id, node_id, status, checkpoint_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET status = excluded.status,
                checkpoint_json = excluded.checkpoint_json, updated_at = excluded.updated_at""",
                (
                    str(checkpoint.id),
                    str(checkpoint.run_id),
                    checkpoint.node_id,
                    checkpoint.status,
                    checkpoint.model_dump_json(),
                    checkpoint.created_at.isoformat(),
                    checkpoint.updated_at.isoformat(),
                ),
            )
        return checkpoint

    def get_checkpoint(self, checkpoint_id: UUID) -> ManualCheckpoint | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT checkpoint_json FROM dag_manual_checkpoints WHERE id = ?", (str(checkpoint_id),)
            ).fetchone()
        return ManualCheckpoint.model_validate_json(row["checkpoint_json"]) if row else None

    def list_checkpoints(self, run_id: UUID) -> list[ManualCheckpoint]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT checkpoint_json FROM dag_manual_checkpoints WHERE run_id = ? ORDER BY created_at",
                (str(run_id),),
            ).fetchall()
        return [ManualCheckpoint.model_validate_json(row["checkpoint_json"]) for row in rows]

    def append_decision(self, decision: ManualCheckpointDecision) -> ManualCheckpointDecision:
        with self.database.connect() as connection:
            checkpoint = connection.execute(
                "SELECT id FROM dag_manual_checkpoints WHERE id = ?", (str(decision.checkpoint_id),)
            ).fetchone()
            if checkpoint is None:
                raise KeyError("DAG_CHECKPOINT_NOT_FOUND")
            if decision.supersedes_event_id is not None:
                prior = connection.execute(
                    "SELECT checkpoint_id FROM dag_checkpoint_decisions WHERE id = ?",
                    (str(decision.supersedes_event_id),),
                ).fetchone()
                if prior is None or prior["checkpoint_id"] != str(decision.checkpoint_id):
                    raise ValueError("DAG_DECISION_SUPERSEDES_INVALID")
            connection.execute(
                """INSERT INTO dag_checkpoint_decisions
                (id, checkpoint_id, action, actor, supersedes_event_id, decision_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(decision.id),
                    str(decision.checkpoint_id),
                    decision.action,
                    decision.actor,
                    str(decision.supersedes_event_id) if decision.supersedes_event_id else None,
                    decision.model_dump_json(),
                    decision.created_at.isoformat(),
                ),
            )
        return decision

    def list_decisions(self, checkpoint_id: UUID) -> list[ManualCheckpointDecision]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT decision_json FROM dag_checkpoint_decisions
                WHERE checkpoint_id = ? ORDER BY created_at, id""",
                (str(checkpoint_id),),
            ).fetchall()
        return [ManualCheckpointDecision.model_validate_json(row["decision_json"]) for row in rows]

    def save_subflow(self, subflow: SubflowDefinition) -> SubflowDefinition:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO dag_subflows
                (id, version, project_id, display_name, definition_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    str(subflow.id),
                    subflow.version,
                    str(subflow.project_id),
                    subflow.display_name,
                    subflow.model_dump_json(),
                    subflow.created_at.isoformat(),
                ),
            )
        return subflow

    def get_subflow(self, subflow_id: UUID, version: int) -> SubflowDefinition | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT definition_json FROM dag_subflows WHERE id = ? AND version = ?",
                (str(subflow_id), version),
            ).fetchone()
        return SubflowDefinition.model_validate_json(row["definition_json"]) if row else None

    def list_subflows(self, project_id: UUID) -> list[SubflowDefinition]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT definition_json FROM dag_subflows WHERE project_id = ? ORDER BY created_at DESC",
                (str(project_id),),
            ).fetchall()
        return [SubflowDefinition.model_validate_json(row["definition_json"]) for row in rows]

    def save_evidence_version(self, evidence: EvidencePackageVersion) -> EvidencePackageVersion:
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO dag_evidence_packages
                (id, run_id, package_version, previous_package_id, sha256, manifest_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(evidence.id),
                    str(evidence.run_id),
                    evidence.package_version,
                    str(evidence.previous_package_id) if evidence.previous_package_id else None,
                    evidence.sha256,
                    evidence.model_dump_json(),
                    evidence.created_at.isoformat(),
                ),
            )
        return evidence

    def list_evidence_versions(self, run_id: UUID) -> list[EvidencePackageVersion]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT manifest_json FROM dag_evidence_packages
                WHERE run_id = ? ORDER BY package_version""",
                (str(run_id),),
            ).fetchall()
        return [EvidencePackageVersion.model_validate_json(row["manifest_json"]) for row in rows]
