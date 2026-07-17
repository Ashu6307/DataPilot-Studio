"""Reproducible Milestone 3A workflow-platform measurements."""

from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from apps.api.app.dag_repository import SQLiteDagRepository
from apps.api.app.database import Database
from packages.contracts import (
    ArtifactType,
    DagEdge,
    DagNode,
    DagOutputDefinition,
    DagPosition,
    DagRunRecord,
    DagRunRequest,
    DagRunStatus,
    DagWorkflow,
    NodeRunRecord,
    NodeRunStatus,
    SubflowDefinition,
    WorkflowLifecycle,
)
from packages.data_engine.reconciliation_exporter import export_reconciliation_evidence
from packages.workflow_dag import build_execution_plan, expand_subflows, validate_dag
from packages.workflow_dag.registry import default_registry
from scripts.benchmark_m2b import fuzzy_and_review


def measure(name: str, operation: Callable[[], Any]) -> tuple[dict[str, Any], Any]:
    tracemalloc.start()
    started = time.perf_counter()
    result = operation()
    duration = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"scenario": name, "duration_seconds": round(duration, 6), "python_peak_bytes": peak}, result


def node(node_id: str, type_id: str, x: float, configuration: dict[str, Any] | None = None) -> DagNode:
    capability = default_registry.require(type_id, 1)
    if configuration is None:
        configuration = (
            {"source_id": str(uuid4()), "overrides": {}} if type_id == "source.saved_dataset" else {"rules": []}
        )
    return DagNode(
        id=node_id,
        node_type_id=type_id,
        display_name=node_id,
        category=capability.category,
        position=DagPosition(x=x, y=100),
        configuration=configuration,
        input_ports=capability.input_ports,
        output_ports=capability.output_ports,
        retry_classification=capability.retry_classification,
        entitlement_capability_id=capability.entitlement_capability_id,
    )


def linear_workflow(count: int) -> DagWorkflow:
    nodes = [node("source", "source.saved_dataset", 0)]
    edges: list[DagEdge] = []
    for index in range(1, count):
        current = node(f"validate_{index:03d}", "validation.rules", index * 220)
        previous = nodes[-1]
        nodes.append(current)
        edges.append(
            DagEdge(
                id=f"edge_{index:03d}",
                source_node_id=previous.id,
                source_port_id="dataset",
                target_node_id=current.id,
                target_port_id="dataset",
                data_contract_reference="canonical_dataset/v1",
            )
        )
    return DagWorkflow(
        project_id=uuid4(),
        display_name=f"Synthetic {count}-node linear workflow",
        lifecycle=WorkflowLifecycle.PUBLISHED,
        nodes=nodes,
        edges=edges,
        outputs=[
            DagOutputDefinition(
                id="output",
                display_name="Output",
                node_id=nodes[-1].id,
                port_id="dataset",
                artifact_type=ArtifactType.CANONICAL_DATASET,
            )
        ],
    )


def branching_workflow() -> DagWorkflow:
    source = node("source", "source.saved_dataset", 0)
    condition = node(
        "condition",
        "control.condition",
        250,
        {"kind": "literal", "value": True, "value_type": "boolean", "field_id": None, "function": None, "args": []},
    )
    true_path = node("true_path", "control.merge", 500, {"strategy": "first_available"})
    false_path = node("false_path", "control.merge", 500, {"strategy": "first_available"})
    false_path.position.y = 300
    edges = [
        DagEdge(
            id="source_condition",
            source_node_id="source",
            source_port_id="dataset",
            target_node_id="condition",
            target_port_id="input",
            data_contract_reference="any/v1",
        ),
        DagEdge(
            id="condition_true",
            source_node_id="condition",
            source_port_id="true",
            target_node_id="true_path",
            target_port_id="branches",
            data_contract_reference="control/v1",
        ),
        DagEdge(
            id="condition_false",
            source_node_id="condition",
            source_port_id="false",
            target_node_id="false_path",
            target_port_id="branches",
            data_contract_reference="control/v1",
        ),
    ]
    return DagWorkflow(
        project_id=uuid4(),
        display_name="Synthetic branch",
        lifecycle=WorkflowLifecycle.PUBLISHED,
        nodes=[source, condition, true_path, false_path],
        edges=edges,
        outputs=[
            DagOutputDefinition(
                id="true_output",
                display_name="True",
                node_id="true_path",
                port_id="output",
                artifact_type=ArtifactType.ANY,
            ),
            DagOutputDefinition(
                id="false_output",
                display_name="False",
                node_id="false_path",
                port_id="output",
                artifact_type=ArtifactType.ANY,
            ),
        ],
    )


def subflow_expansion() -> tuple[DagWorkflow, dict[tuple[UUID, int], SubflowDefinition]]:
    source = node("inner_source", "source.saved_dataset", 0)
    current = source
    children = [source]
    edges: list[DagEdge] = []
    for index in range(1, 20):
        child = node(f"inner_{index}", "validation.rules", index * 200)
        children.append(child)
        edges.append(
            DagEdge(
                id=f"inner_edge_{index}",
                source_node_id=current.id,
                source_port_id="dataset",
                target_node_id=child.id,
                target_port_id="dataset",
                data_contract_reference="canonical_dataset/v1",
            )
        )
        current = child
    subflow = SubflowDefinition(
        project_id=uuid4(),
        display_name="Synthetic subflow",
        public_input_ports=[],
        public_output_ports=current.output_ports,
        nodes=children,
        edges=edges,
    )
    reference = node(
        "subflow",
        "subflow.reference",
        0,
        {
            "subflow_id": str(subflow.id),
            "subflow_version": 1,
            "input_bindings": {},
            "output_bindings": {"output": f"{current.id}.dataset"},
        },
    )
    root = DagWorkflow(
        project_id=subflow.project_id,
        display_name="Subflow root",
        nodes=[reference],
        edges=[],
        outputs=[
            DagOutputDefinition(
                id="output", display_name="Output", node_id="subflow", port_id="output", artifact_type=ArtifactType.ANY
            )
        ],
    )
    return root, {(subflow.id, 1): subflow}


def persistence_and_recovery(root: Path) -> list[dict[str, Any]]:
    database = Database(root / "metadata.sqlite3")
    database.initialize()
    workflow = linear_workflow(25)
    now = datetime.now(UTC).isoformat()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)",
            (str(workflow.project_id), "Benchmark", "en-IN", "local_only", now, now),
        )
    repository = SQLiteDagRepository(database)
    persist_metric, _ = measure("workflow_persistence_25_nodes", lambda: repository.save_workflow(workflow))
    plan = repository.save_plan(build_execution_plan(workflow))
    run = DagRunRecord(
        project_id=workflow.project_id,
        workflow_id=workflow.id,
        workflow_version=1,
        plan_id=plan.id,
        status=DagRunStatus.RUNNING,
    )
    repository.create_run(run, DagRunRequest(workflow=workflow))

    def state_updates() -> None:
        for index in range(100):
            repository.save_node_run(
                NodeRunRecord(
                    run_id=run.id,
                    node_id="source",
                    node_type_id="source.saved_dataset",
                    attempt=index + 1,
                    status=NodeRunStatus.SUCCEEDED,
                )
            )

    update_metric, _ = measure("node_state_updates_100", state_updates)
    recovery_metric, recovered = measure("restart_recovery_one_run", repository.recover_orphans)
    recovery_metric["recovered_runs"] = len(recovered)
    return [persist_metric, update_metric, recovery_metric]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    results: list[dict[str, Any]] = []
    metric, plan_25 = measure("planning_25_node_linear", lambda: build_execution_plan(linear_workflow(25)))
    metric["nodes"] = len(plan_25.nodes)
    results.append(metric)
    metric, validation_100 = measure("validation_100_node_linear", lambda: validate_dag(linear_workflow(100)))
    metric["nodes"] = len(validation_100.topological_order)
    metric["valid"] = validation_100.valid
    results.append(metric)
    metric, branch_plan = measure("branching_workflow_planning", lambda: build_execution_plan(branching_workflow()))
    metric["parallel_groups"] = max(node.parallel_group for node in branch_plan.nodes)
    results.append(metric)
    root, definitions = subflow_expansion()
    metric, expanded = measure("subflow_expansion_20_nodes", lambda: expand_subflows(root, definitions))
    metric["expanded_nodes"] = len(expanded.nodes)
    results.append(metric)
    with tempfile.TemporaryDirectory() as temporary:
        temporary_root = Path(temporary)
        results.extend(persistence_and_recovery(temporary_root))
        _, (reconciliation_workflow, reconciliation_result) = fuzzy_and_review(50)
        first = temporary_root / "evidence-v1"
        export_reconciliation_evidence(first, reconciliation_result, reconciliation_workflow)
        evidence_metric, manifest = measure(
            "evidence_regeneration_from_result_checkpoint",
            lambda: export_reconciliation_evidence(
                temporary_root / "evidence-v2", reconciliation_result, reconciliation_workflow
            ),
        )
        evidence_metric["output_entries"] = len(manifest.entries)
        results.append(evidence_metric)
    payload = {
        "measured_at": datetime.now(UTC).isoformat(),
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "logical_cores": os.cpu_count(),
            "python": platform.python_version(),
        },
        "workflow_characteristics": (
            "synthetic typed DAGs with closed registry nodes; evidence regeneration "
            "reuses an existing reconciliation result"
        ),
        "results": results,
        "limitations": [
            "tracemalloc excludes native-library allocations and is not complete process RSS",
            "UI canvas interaction is measured separately by Playwright because this script does not execute a browser",
            "evidence regeneration timing excludes matching and includes only deterministic export "
            "from checkpointed result state",
        ],
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
