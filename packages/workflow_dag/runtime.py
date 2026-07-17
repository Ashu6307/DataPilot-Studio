"""Background DAG execution with isolated artifacts and resumable node checkpoints."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import polars as pl
from pydantic import BaseModel

from packages.contracts import (
    ArtifactReference,
    ArtifactType,
    DagJobSubmission,
    DagNode,
    DagRunRecord,
    DagRunRequest,
    DagRunStatus,
    ExecutionPlan,
    ManualCheckpoint,
    ManualCheckpointDecision,
    ManualCheckpointStatus,
    ManualCheckpointType,
    NodeRunRecord,
    NodeRunStatus,
    PlannedNode,
    SubflowDefinition,
    WorkflowLifecycle,
)

from .adapters import DagAdapterRegistry, RuntimeControl
from .parameters import resolve_runtime_parameters, substitute_parameters
from .planner import build_execution_plan
from .registry import NodeCapabilityRegistry, default_registry
from .subflows import SubflowKey, expand_subflows


class DagExecutionStore(Protocol):
    def save_workflow(self, workflow: Any) -> Any: ...
    def save_plan(self, plan: ExecutionPlan) -> ExecutionPlan: ...
    def get_plan(self, plan_id: UUID) -> ExecutionPlan | None: ...
    def create_run(self, run: DagRunRecord, request: DagRunRequest) -> DagRunRecord: ...
    def get_request(self, run_id: UUID) -> DagRunRequest | None: ...
    def get_run(self, run_id: UUID) -> DagRunRecord | None: ...
    def update_run(self, run: DagRunRecord) -> DagRunRecord: ...
    def list_node_runs(self, run_id: UUID) -> list[NodeRunRecord]: ...
    def save_node_run(self, record: NodeRunRecord) -> NodeRunRecord: ...
    def save_artifacts(self, run_id: UUID, artifacts: list[ArtifactReference]) -> None: ...
    def save_checkpoint(self, checkpoint: ManualCheckpoint) -> ManualCheckpoint: ...
    def list_checkpoints(self, run_id: UUID) -> list[ManualCheckpoint]: ...
    def list_decisions(self, checkpoint_id: UUID) -> list[ManualCheckpointDecision]: ...
    def recover_orphans(self) -> list[DagRunRecord]: ...
    def get_subflow(self, subflow_id: UUID, version: int) -> SubflowDefinition | None: ...


class DagRunCancelled(RuntimeError):
    pass


class _Control(RuntimeControl):
    def __init__(self, store: DagExecutionStore, run_id: UUID, artifact_root: Path) -> None:
        self.store = store
        self.run_id = run_id
        self.artifact_root = artifact_root

    def check_cancelled(self) -> None:
        run = self.store.get_run(self.run_id)
        if run is None:
            raise DagRunCancelled("DAG_RUN_NOT_FOUND")
        if run.cancel_requested or run.status in {DagRunStatus.CANCELLING, DagRunStatus.CANCELLED}:
            raise DagRunCancelled("DAG_RUN_CANCELLED_BY_USER")

    def progress(self, node_id: str, rows_processed: int, estimated_rows: int | None, message: str) -> None:
        run = self.store.get_run(self.run_id)
        if run is None:
            return
        # Detailed row metrics belong to node records; run progress remains DAG-node based.
        updated = run.model_copy(
            update={
                "current_node_id": node_id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.store.update_run(updated)

    def output_directory(self, node_id: str) -> Path:
        directory = (self.artifact_root / "outputs" / _safe_name(node_id)).resolve()
        if self.artifact_root.resolve() not in directory.parents:
            raise ValueError("DAG_OUTPUT_PATH_ESCAPE")
        directory.mkdir(parents=True, exist_ok=True)
        return directory


def _safe_name(value: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for character in value):
        raise ValueError("DAG_ARTIFACT_NAME_UNSAFE")
    return value


def _write_artifact(root: Path, node_id: str, port_id: str, value: Any, artifact_type: Any) -> ArtifactReference:
    safe_node = _safe_name(node_id)
    safe_port = _safe_name(port_id)
    directory = root / "artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{safe_node}--{safe_port}"
    row_count: int | None = None
    if isinstance(value, Path):
        path = value.resolve()
        if root.resolve() not in path.parents or not path.is_file():
            raise ValueError("DAG_OUTPUT_ARTIFACT_PATH_UNSAFE")
        kind = "materialised_file"
    elif isinstance(value, pl.DataFrame):
        path = directory / f"{stem}.parquet"
        value.write_parquet(path)
        row_count = value.height
        kind = "polars_dataframe"
    else:
        path = directory / f"{stem}.json"
        if isinstance(value, BaseModel):
            payload = value.model_dump(mode="json")
            kind = f"pydantic:{value.__class__.__name__}"
        else:
            payload = value
            kind = type(value).__name__
        path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
        if isinstance(value, list):
            row_count = len(value)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    relative_path = path.relative_to(root).as_posix()
    return ArtifactReference(
        artifact_type=artifact_type,
        producer_node_id=node_id,
        path_reference=relative_path,
        sha256=digest,
        row_count=row_count,
        metadata={"port_id": port_id, "value_kind": kind},
    )


def _read_artifact(root: Path, artifact: ArtifactReference) -> Any:
    if artifact.path_reference is None:
        raise ValueError("DAG_ARTIFACT_NOT_MATERIALISED")
    path = (root / artifact.path_reference).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("DAG_ARTIFACT_PATH_ESCAPE")
    if not path.exists():
        raise FileNotFoundError(f"DAG_ARTIFACT_MISSING:{artifact.artifact_id}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
        raise ValueError("DAG_ARTIFACT_FINGERPRINT_MISMATCH")
    if artifact.metadata.get("value_kind") == "materialised_file":
        return path
    if path.suffix == ".parquet":
        return pl.read_parquet(path)
    return json.loads(path.read_text(encoding="utf-8"))


class LocalDagExecutor:
    """Local background executor; every full DAG run enters through ``submit``."""

    def __init__(
        self,
        store: DagExecutionStore,
        adapters: DagAdapterRegistry,
        workspace: Path,
        capabilities: NodeCapabilityRegistry = default_registry,
        max_workers: int = 1,
    ) -> None:
        self.store = store
        self.adapters = adapters
        self.workspace = workspace.resolve()
        self.capabilities = capabilities
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="datapilot-dag")
        self._futures: dict[UUID, Future[None]] = {}
        self._lock = threading.Lock()
        self.store.recover_orphans()

    def submit(self, submission: DagJobSubmission) -> DagRunRecord:
        original_request = submission.request
        if original_request.workflow.lifecycle != WorkflowLifecycle.PUBLISHED:
            raise ValueError("DAG_WORKFLOW_MUST_BE_PUBLISHED")
        if submission.retry_of is None and submission.recovery_of is None:
            self.store.save_workflow(original_request.workflow)
        definitions: dict[SubflowKey, SubflowDefinition] = {}

        def collect(subflow_id: UUID, version: int) -> None:
            key = (subflow_id, version)
            if key in definitions:
                return
            definition = self.store.get_subflow(subflow_id, version)
            if definition is None:
                raise ValueError(f"DAG_SUBFLOW_VERSION_MISSING:{subflow_id}:{version}")
            definitions[key] = definition
            for dependency_id, dependency_version in definition.dependencies:
                collect(dependency_id, dependency_version)

        for node in original_request.workflow.nodes:
            if node.node_type_id == "subflow.reference":
                collect(UUID(str(node.configuration["subflow_id"])), int(node.configuration["subflow_version"]))
        executable_workflow = (
            expand_subflows(original_request.workflow, definitions) if definitions else original_request.workflow
        )
        request = original_request.model_copy(update={"workflow": executable_workflow})
        plan = build_execution_plan(request.workflow, request.parameters, self.capabilities)
        node_by_id = {node.id: node for node in request.workflow.nodes}
        for planned in plan.nodes:
            node = node_by_id[planned.node_id]
            if planned.manual_checkpoint:
                continue
            capability = self.capabilities.require(node.node_type_id, node.node_version)
            self.adapters.require(capability.execution_adapter_id)
        self.store.save_plan(plan)
        _, parameter_audit = resolve_runtime_parameters(
            request.workflow.input_parameters,
            request.parameters,
            request.workflow.resource_policy,
        )
        run = DagRunRecord(
            project_id=request.workflow.project_id,
            workflow_id=request.workflow.id,
            workflow_version=request.workflow.version,
            plan_id=plan.id,
            parameter_audit=parameter_audit,
            retry_of=submission.retry_of,
            recovery_of=submission.recovery_of,
        )
        self.store.create_run(run, request)
        self._schedule(run.id)
        return run

    def _schedule(self, run_id: UUID) -> None:
        with self._lock:
            current = self._futures.get(run_id)
            if current is not None and not current.done():
                raise ValueError("DAG_RUN_ALREADY_ACTIVE")
            self._futures[run_id] = self.executor.submit(self._run, run_id)

    def _run_root(self, run_id: UUID, completed: bool = False) -> Path:
        state = "completed" if completed else "partial"
        root = self.workspace / "dag-runs" / state / str(run_id)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _run(self, run_id: UUID) -> None:
        run = self.store.get_run(run_id)
        request = self.store.get_request(run_id)
        if run is None or request is None:
            return
        now = datetime.now(UTC)
        run = run.model_copy(
            update={
                "status": DagRunStatus.RUNNING,
                "started_at": run.started_at or now,
                "error_code": None,
                "error_message": None,
                "updated_at": now,
            }
        )
        self.store.update_run(run)
        partial_root = self._run_root(run_id)
        control = _Control(self.store, run_id, partial_root)
        try:
            plan = self.store.get_plan(run.plan_id)
            if plan is None:
                raise ValueError("DAG_EXECUTION_PLAN_MISSING")
            resolved, _ = resolve_runtime_parameters(
                request.workflow.input_parameters,
                request.parameters,
                request.workflow.resource_policy,
            )
            workflow = request.workflow.model_copy(deep=True)
            for node in workflow.nodes:
                node.configuration = substitute_parameters(node.configuration, resolved)
            node_by_id = {node.id: node for node in workflow.nodes}
            edge_inputs: dict[str, list[Any]] = defaultdict(list)
            output_values: dict[tuple[str, str], Any] = {}
            completed_nodes = set(run.completed_node_ids)
            for prior in self.store.list_node_runs(run_id):
                if prior.status not in {NodeRunStatus.SUCCEEDED, NodeRunStatus.RECOVERED}:
                    continue
                for artifact in prior.output_artifacts:
                    port_id = str(artifact.metadata.get("port_id", ""))
                    output_values[(prior.node_id, port_id)] = _read_artifact(partial_root, artifact)
            for edge in workflow.edges:
                value = output_values.get((edge.source_node_id, edge.source_port_id))
                if value is not None:
                    edge_inputs[f"{edge.target_node_id}:{edge.target_port_id}"].append(value)
            parallel_starts = [
                planned
                for planned in plan.nodes
                if not planned.dependency_node_ids
                and planned.node_id not in completed_nodes
                and not planned.manual_checkpoint
            ]
            if len(parallel_starts) > 1:

                def execute_start(
                    planned: PlannedNode,
                ) -> tuple[PlannedNode, DagNode, NodeRunRecord, dict[str, Any]]:
                    control.check_cancelled()
                    start_node = node_by_id[planned.node_id]
                    start_record = NodeRunRecord(
                        run_id=run_id,
                        node_id=start_node.id,
                        node_type_id=start_node.node_type_id,
                        status=NodeRunStatus.RUNNING,
                        started_at=datetime.now(UTC),
                    )
                    self.store.save_node_run(start_record)
                    capability = self.capabilities.require(start_node.node_type_id, start_node.node_version)
                    adapter = self.adapters.require(capability.execution_adapter_id)
                    return planned, start_node, start_record, adapter(start_node, {}, control)

                workers = min(
                    len(parallel_starts),
                    workflow.resource_policy.maximum_concurrent_ready_nodes,
                )
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="datapilot-dag-node") as pool:
                    parallel_results = list(pool.map(execute_start, parallel_starts))
                for _, start_node, start_record, start_outputs in parallel_results:
                    start_references: list[ArtifactReference] = []
                    for port_id, value in start_outputs.items():
                        port = next((item for item in start_node.output_ports if item.id == port_id), None)
                        if port is None:
                            raise ValueError(f"DAG_ADAPTER_OUTPUT_PORT_INVALID:{start_node.id}:{port_id}")
                        reference = _write_artifact(
                            partial_root,
                            start_node.id,
                            port_id,
                            value,
                            port.artifact_type,
                        )
                        start_references.append(reference)
                        output_values[(start_node.id, port_id)] = value
                        for edge in workflow.edges:
                            if edge.source_node_id == start_node.id and edge.source_port_id == port_id:
                                edge_inputs[f"{edge.target_node_id}:{edge.target_port_id}"].append(value)
                    self.store.save_artifacts(run_id, start_references)
                    completed_nodes.add(start_node.id)
                    self.store.save_node_run(
                        start_record.model_copy(
                            update={
                                "status": NodeRunStatus.SUCCEEDED,
                                "output_artifacts": start_references,
                                "progress_percent": 100,
                                "ended_at": datetime.now(UTC),
                                "updated_at": datetime.now(UTC),
                            }
                        )
                    )
                latest_run = self.store.get_run(run_id) or run
                self.store.update_run(
                    latest_run.model_copy(
                        update={
                            "completed_node_ids": sorted(completed_nodes),
                            "progress_percent": len(completed_nodes) * 100 / max(len(plan.nodes), 1),
                            "updated_at": datetime.now(UTC),
                        }
                    )
                )
            for planned in plan.nodes:
                if planned.node_id in completed_nodes:
                    continue
                control.check_cancelled()
                node = node_by_id[planned.node_id]
                run = self.store.get_run(run_id) or run
                progress = len(completed_nodes) * 100 / max(len(plan.nodes), 1)
                run = run.model_copy(
                    update={
                        "current_node_id": node.id,
                        "current_parallel_group": planned.parallel_group,
                        "progress_percent": progress,
                        "updated_at": datetime.now(UTC),
                    }
                )
                self.store.update_run(run)
                inputs = {port.id: list(edge_inputs.get(f"{node.id}:{port.id}", [])) for port in node.input_ports}
                missing_required = [port.id for port in node.input_ports if port.required and not inputs[port.id]]
                if missing_required:
                    skipped = NodeRunRecord(
                        run_id=run_id,
                        node_id=node.id,
                        node_type_id=node.node_type_id,
                        status=NodeRunStatus.SKIPPED,
                        error_code="DAG_BRANCH_INPUT_NOT_SELECTED",
                        error_message=f"Inactive branch left inputs unavailable: {sorted(missing_required)}",
                        progress_percent=100,
                        started_at=datetime.now(UTC),
                        ended_at=datetime.now(UTC),
                    )
                    self.store.save_node_run(skipped)
                    latest_run = self.store.get_run(run_id) or run
                    skipped_nodes = sorted({*latest_run.skipped_node_ids, node.id})
                    self.store.update_run(
                        latest_run.model_copy(
                            update={
                                "skipped_node_ids": skipped_nodes,
                                "progress_percent": (len(completed_nodes) + len(skipped_nodes))
                                * 100
                                / max(len(plan.nodes), 1),
                                "updated_at": datetime.now(UTC),
                            }
                        )
                    )
                    continue
                record = NodeRunRecord(
                    run_id=run_id,
                    node_id=node.id,
                    node_type_id=node.node_type_id,
                    status=NodeRunStatus.RUNNING,
                    started_at=datetime.now(UTC),
                )
                self.store.save_node_run(record)
                if planned.manual_checkpoint:
                    checkpoint = next(
                        (item for item in self.store.list_checkpoints(run_id) if item.node_id == node.id), None
                    )
                    if checkpoint is None:
                        checkpoint = ManualCheckpoint(
                            run_id=run_id,
                            node_id=node.id,
                            checkpoint_type=ManualCheckpointType(
                                node.configuration.get("checkpoint_type", "output_publication_approval")
                            ),
                            reason=str(node.configuration.get("reason", "Manual review is required.")),
                            evidence_summary={
                                "input_artifact_count": sum(len(values) for values in inputs.values()),
                                "node_type_id": node.node_type_id,
                            },
                            available_actions=["approve", "reject", "edit_rerun", "skip", "cancel"],
                        )
                        self.store.save_checkpoint(checkpoint)
                    decisions = self.store.list_decisions(checkpoint.id)
                    latest = decisions[-1] if decisions else None
                    if latest is None:
                        waiting_record = record.model_copy(
                            update={"status": NodeRunStatus.WAITING, "updated_at": datetime.now(UTC)}
                        )
                        self.store.save_node_run(waiting_record)
                        self.store.update_run(
                            run.model_copy(
                                update={
                                    "status": DagRunStatus.WAITING_FOR_REVIEW,
                                    "updated_at": datetime.now(UTC),
                                }
                            )
                        )
                        return
                    if latest.action not in {"approve", "skip"}:
                        raise ValueError(f"DAG_MANUAL_CHECKPOINT_{latest.action.upper()}")
                    values = next((values for values in inputs.values() if values), [])
                    outputs: dict[str, Any] = {}
                    for output_port in node.output_ports:
                        if output_port.artifact_type == ArtifactType.REVIEW_DECISIONS:
                            outputs[output_port.id] = decisions
                        elif values:
                            outputs[output_port.id] = values[0]
                    checkpoint = checkpoint.model_copy(
                        update={
                            "status": (
                                ManualCheckpointStatus.APPROVED
                                if latest.action == "approve"
                                else ManualCheckpointStatus.SKIPPED
                            ),
                            "decision_event_ids": [item.id for item in decisions],
                            "updated_at": datetime.now(UTC),
                        }
                    )
                    self.store.save_checkpoint(checkpoint)
                else:
                    capability = self.capabilities.require(node.node_type_id, node.node_version)
                    adapter = self.adapters.require(capability.execution_adapter_id)
                    outputs = adapter(node, inputs, control)
                references: list[ArtifactReference] = []
                for port_id, value in outputs.items():
                    port = next((item for item in node.output_ports if item.id == port_id), None)
                    if port is None:
                        raise ValueError(f"DAG_ADAPTER_OUTPUT_PORT_INVALID:{node.id}:{port_id}")
                    reference = _write_artifact(partial_root, node.id, port_id, value, port.artifact_type)
                    references.append(reference)
                    output_values[(node.id, port_id)] = value
                    for edge in workflow.edges:
                        if edge.source_node_id == node.id and edge.source_port_id == port_id:
                            edge_inputs[f"{edge.target_node_id}:{edge.target_port_id}"].append(value)
                self.store.save_artifacts(run_id, references)
                completed_nodes.add(node.id)
                self.store.save_node_run(
                    record.model_copy(
                        update={
                            "status": NodeRunStatus.SUCCEEDED,
                            "output_artifacts": references,
                            "progress_percent": 100,
                            "ended_at": datetime.now(UTC),
                            "updated_at": datetime.now(UTC),
                        }
                    )
                )
                latest_run = self.store.get_run(run_id) or run
                self.store.update_run(
                    latest_run.model_copy(
                        update={
                            "completed_node_ids": sorted(completed_nodes),
                            "progress_percent": len(completed_nodes) * 100 / max(len(plan.nodes), 1),
                            "updated_at": datetime.now(UTC),
                        }
                    )
                )
            completed_root = self._run_root(run_id, completed=True)
            if any(completed_root.iterdir()):
                raise FileExistsError("DAG_COMPLETED_OUTPUT_ALREADY_EXISTS")
            completed_root.rmdir()
            completed_root.parent.mkdir(parents=True, exist_ok=True)
            partial_root.replace(completed_root)
            final = self.store.get_run(run_id) or run
            self.store.update_run(
                final.model_copy(
                    update={
                        "status": DagRunStatus.SUCCEEDED,
                        "current_node_id": None,
                        "current_parallel_group": None,
                        "progress_percent": 100,
                        "output_available": True,
                        "completed_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                    }
                )
            )
        except DagRunCancelled as error:
            current = self.store.get_run(run_id) or run
            self.store.update_run(
                current.model_copy(
                    update={
                        "status": DagRunStatus.CANCELLED,
                        "output_available": False,
                        "error_code": "DAG_RUN_CANCELLED",
                        "error_message": str(error),
                        "completed_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                    }
                )
            )
        except Exception as error:
            current = self.store.get_run(run_id) or run
            self.store.update_run(
                current.model_copy(
                    update={
                        "status": DagRunStatus.FAILED,
                        "output_available": False,
                        "error_code": type(error).__name__.upper(),
                        "error_message": str(error),
                        "completed_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                    }
                )
            )

    def cancel(self, run_id: UUID) -> DagRunRecord:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError("DAG_RUN_NOT_FOUND")
        if run.status in {DagRunStatus.SUCCEEDED, DagRunStatus.FAILED, DagRunStatus.CANCELLED}:
            return run
        return self.store.update_run(
            run.model_copy(
                update={
                    "status": DagRunStatus.CANCELLING,
                    "cancel_requested": True,
                    "updated_at": datetime.now(UTC),
                }
            )
        )

    def resume(self, run_id: UUID) -> DagRunRecord:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError("DAG_RUN_NOT_FOUND")
        if run.status not in {DagRunStatus.WAITING_FOR_REVIEW, DagRunStatus.RECOVERY_REQUIRED}:
            raise ValueError("DAG_RUN_NOT_RESUMABLE")
        updated = self.store.update_run(
            run.model_copy(
                update={
                    "status": DagRunStatus.QUEUED,
                    "cancel_requested": False,
                    "updated_at": datetime.now(UTC),
                }
            )
        )
        self._schedule(run_id)
        return updated

    def retry(self, run_id: UUID) -> DagRunRecord:
        run = self.store.get_run(run_id)
        request = self.store.get_request(run_id)
        plan = self.store.get_plan(run.plan_id) if run is not None else None
        if run is None or request is None or plan is None:
            raise KeyError("DAG_RUN_NOT_FOUND")
        if run.status not in {DagRunStatus.FAILED, DagRunStatus.CANCELLED}:
            raise ValueError("DAG_RUN_RETRY_STATUS_INVALID")
        if plan.non_retryable_nodes:
            raise ValueError("DAG_RUN_RETRY_NOT_DETERMINISTIC")
        return self.submit(DagJobSubmission(request=request, retry_of=run.id))

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
