"""Deterministic execution planning for validated workflow DAGs."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from packages.contracts import (
    DagWorkflow,
    ExecutionPlan,
    NodeCategory,
    PlannedNode,
    RuntimeParameterValue,
)

from .parameters import resolve_runtime_parameters
from .registry import AllowAllEntitlements, EntitlementProvider, NodeCapabilityRegistry, default_registry
from .validation import validate_dag


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_sum(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def build_execution_plan(
    workflow: DagWorkflow,
    parameter_overrides: list[RuntimeParameterValue] | None = None,
    registry: NodeCapabilityRegistry = default_registry,
    entitlements: EntitlementProvider | None = None,
) -> ExecutionPlan:
    """Validate and compile a stable topological execution plan.

    Plain secret values never enter a plan. Credential parameters are opaque
    references and the parameter fingerprint is the only parameter material
    retained by this contract.
    """

    validation = validate_dag(workflow, registry, entitlements or AllowAllEntitlements())
    if not validation.valid:
        codes = sorted({finding.reason_code for finding in validation.findings})
        raise ValueError(f"DAG_VALIDATION_FAILED:{','.join(codes)}")
    resolved, _ = resolve_runtime_parameters(
        workflow.input_parameters,
        parameter_overrides or [],
        workflow.resource_policy,
    )
    parameter_fingerprint = _fingerprint(resolved)
    node_by_id = {node.id: node for node in workflow.nodes}
    dependencies: dict[str, list[str]] = defaultdict(list)
    consumers: dict[tuple[str, str], int] = defaultdict(int)
    for edge in workflow.edges:
        dependencies[edge.target_node_id].append(edge.source_node_id)
        consumers[(edge.source_node_id, edge.source_port_id)] += 1
    declared_outputs = {(output.node_id, output.port_id) for output in workflow.outputs}
    parallel_groups: dict[str, int] = {}
    planned_nodes: list[PlannedNode] = []
    for sequence, node_id in enumerate(validation.topological_order, start=1):
        node = node_by_id[node_id]
        dependency_ids = sorted(set(dependencies[node_id]))
        parallel_group = 1 + max((parallel_groups[item] for item in dependency_ids), default=0)
        parallel_groups[node_id] = parallel_group
        dead_ports = sorted(
            port.id
            for port in node.output_ports
            if consumers[(node.id, port.id)] == 0 and (node.id, port.id) not in declared_outputs
        )
        planned_nodes.append(
            PlannedNode(
                node_id=node.id,
                sequence=sequence,
                dependency_node_ids=dependency_ids,
                parallel_group=parallel_group,
                retry_classification=node.retry_classification,
                checkpoint_policy=node.checkpoint_policy,
                resource_estimate=node.resource_estimate,
                output_consumer_count=sum(consumers[(node.id, port.id)] for port in node.output_ports),
                dead_output_ports=dead_ports,
                manual_checkpoint=(
                    node.node_type_id == "control.manual_approval"
                    or node.retry_classification.value == "manual_review_required"
                    or node.checkpoint_policy.value == "manual_checkpoint"
                ),
            )
        )
    warnings: list[str] = []
    for node in workflow.nodes:
        if node.resource_estimate.risk in {"warning", "block"}:
            warnings.append(f"{node.id}:{node.resource_estimate.risk}")
    plan_basis = {
        "workflow_id": str(workflow.id),
        "workflow_version": workflow.version,
        "parameter_fingerprint": parameter_fingerprint,
        "nodes": [item.model_dump(mode="json") for item in planned_nodes],
        "outputs": [item.model_dump(mode="json") for item in workflow.outputs],
    }
    return ExecutionPlan(
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        parameter_fingerprint=parameter_fingerprint,
        plan_fingerprint=_fingerprint(plan_basis),
        nodes=planned_nodes,
        estimated_sources=sum(node.category == NodeCategory.SOURCE for node in workflow.nodes),
        estimated_rows=_optional_sum([node.resource_estimate.estimated_rows for node in workflow.nodes]),
        estimated_candidate_pairs=_optional_sum(
            [node.resource_estimate.estimated_candidate_pairs for node in workflow.nodes]
        ),
        estimated_outputs=len(workflow.outputs),
        resource_warnings=sorted(warnings),
        manual_checkpoint_nodes=[item.node_id for item in planned_nodes if item.manual_checkpoint],
        non_retryable_nodes=[
            item.node_id for item in planned_nodes if item.retry_classification.value == "non_retryable"
        ],
    )
