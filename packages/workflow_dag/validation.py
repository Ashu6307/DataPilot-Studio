"""Static DAG validation before planning or execution."""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque

from packages.contracts import (
    ArtifactType,
    DagEdge,
    DagValidationFinding,
    DagValidationResult,
    DagWorkflow,
    Severity,
)
from packages.workflow_schema import assert_secret_free

from .configuration import validate_node_configuration
from .parameters import referenced_parameter_ids, substitute_parameters
from .registry import AllowAllEntitlements, EntitlementProvider, NodeCapabilityRegistry, default_registry


def _finding(
    reason: str,
    explanation: str,
    resolution: str,
    *,
    severity: Severity = Severity.BLOCKING,
    node_id: str | None = None,
    edge_id: str | None = None,
    parameter_id: str | None = None,
) -> DagValidationFinding:
    return DagValidationFinding(
        severity=severity,
        reason_code=reason,
        explanation=explanation,
        suggested_resolution=resolution,
        node_id=node_id,
        edge_id=edge_id,
        parameter_id=parameter_id,
    )


def _compatible(source: ArtifactType, target: ArtifactType) -> bool:
    return source == target or source == ArtifactType.ANY or target == ArtifactType.ANY


def _topological(
    node_ids: list[str], edges: list[DagEdge]
) -> tuple[list[str], set[str], dict[str, list[str]], dict[str, int]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        if edge.source_node_id in indegree and edge.target_node_id in indegree:
            adjacency[edge.source_node_id].append(edge.target_node_id)
            indegree[edge.target_node_id] += 1
    original_indegree = dict(indegree)
    queue = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for target in sorted(adjacency[current]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    reachable: set[str] = set()
    frontier = deque(sorted(node_id for node_id, count in original_indegree.items() if count == 0))
    while frontier:
        current = frontier.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        frontier.extend(adjacency[current])
    return order, reachable, adjacency, original_indegree


def validate_dag(
    workflow: DagWorkflow,
    registry: NodeCapabilityRegistry = default_registry,
    entitlements: EntitlementProvider | None = None,
) -> DagValidationResult:
    findings: list[DagValidationFinding] = []
    entitlement_provider = entitlements or AllowAllEntitlements()
    payload = workflow.model_dump(mode="json")
    try:
        assert_secret_free(payload)
    except ValueError as error:
        findings.append(_finding("DAG_PLAIN_TEXT_SECRET", str(error), "Replace the value with a credential reference."))
    payload_bytes = len(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    if payload_bytes > workflow.resource_policy.maximum_payload_bytes:
        findings.append(
            _finding(
                "DAG_PAYLOAD_LIMIT_EXCEEDED",
                f"Workflow payload is {payload_bytes} bytes.",
                "Remove redundant configuration or increase the reviewed budget.",
            )
        )
    if len(workflow.nodes) > workflow.resource_policy.maximum_nodes:
        findings.append(
            _finding(
                "DAG_NODE_LIMIT_EXCEEDED",
                "Workflow exceeds its node budget.",
                "Split the workflow into reviewed subflows.",
            )
        )
    if len(workflow.edges) > workflow.resource_policy.maximum_edges:
        findings.append(
            _finding(
                "DAG_EDGE_LIMIT_EXCEEDED",
                "Workflow exceeds its edge budget.",
                "Remove redundant edges or split the workflow.",
            )
        )
    node_counts = Counter(node.id for node in workflow.nodes)
    edge_counts = Counter(edge.id for edge in workflow.edges)
    for node_id, count in node_counts.items():
        if count > 1:
            findings.append(
                _finding(
                    "DAG_NODE_ID_DUPLICATE",
                    f"Node ID {node_id} appears {count} times.",
                    "Assign a stable unique node ID.",
                    node_id=node_id,
                )
            )
    for edge_id, count in edge_counts.items():
        if count > 1:
            findings.append(
                _finding(
                    "DAG_EDGE_ID_DUPLICATE",
                    f"Edge ID {edge_id} appears {count} times.",
                    "Assign a stable unique edge ID.",
                    edge_id=edge_id,
                )
            )
    node_by_id = {node.id: node for node in workflow.nodes}
    parameter_defaults = {parameter.id: parameter.default_value for parameter in workflow.input_parameters}
    incoming_ports: dict[tuple[str, str], int] = Counter()
    valid_edges: list[DagEdge] = []
    for node in workflow.nodes:
        capability = registry.get(node.node_type_id, node.node_version)
        if capability is None:
            findings.append(
                _finding(
                    "DAG_NODE_VERSION_UNSUPPORTED",
                    f"No registered capability for {node.node_type_id} v{node.node_version}.",
                    "Install the required signed capability or select a supported version.",
                    node_id=node.id,
                )
            )
            continue
        if node.category != capability.category:
            findings.append(
                _finding(
                    "DAG_NODE_CATEGORY_INVALID",
                    "Node category does not match its registered capability.",
                    "Recreate the node from the capability palette.",
                    node_id=node.id,
                )
            )
        if not entitlement_provider.has_capability(capability.entitlement_capability_id):
            findings.append(
                _finding(
                    "DAG_ENTITLEMENT_MISSING",
                    f"Capability {capability.entitlement_capability_id} is unavailable.",
                    "Use an available provider entitlement or remove the node.",
                    node_id=node.id,
                )
            )
        try:
            configuration = substitute_parameters(node.configuration, parameter_defaults)
            validate_node_configuration(capability.configuration_schema, configuration)
        except (KeyError, ValueError) as error:
            findings.append(
                _finding(
                    "DAG_NODE_CONFIGURATION_INVALID",
                    f"Node configuration does not satisfy {capability.configuration_schema}: {error}",
                    "Correct the highlighted configuration fields before execution.",
                    node_id=node.id,
                )
            )
        expected_inputs = {(port.id, port.artifact_type) for port in capability.input_ports}
        expected_outputs = {(port.id, port.artifact_type) for port in capability.output_ports}
        if {(port.id, port.artifact_type) for port in node.input_ports} != expected_inputs or {
            (port.id, port.artifact_type) for port in node.output_ports
        } != expected_outputs:
            findings.append(
                _finding(
                    "DAG_NODE_PORT_CONTRACT_INVALID",
                    "Node ports differ from the registered version.",
                    "Refresh this node from the capability registry.",
                    node_id=node.id,
                )
            )
        referenced = referenced_parameter_ids(node.configuration)
        defined = {parameter.id for parameter in workflow.input_parameters}
        for parameter_id in sorted(referenced - defined):
            findings.append(
                _finding(
                    "DAG_PARAMETER_REFERENCE_INVALID",
                    f"Configuration references unknown parameter {parameter_id}.",
                    "Create the parameter or remove the reference.",
                    node_id=node.id,
                    parameter_id=parameter_id,
                )
            )
    for edge in workflow.edges:
        source = node_by_id.get(edge.source_node_id)
        target = node_by_id.get(edge.target_node_id)
        if source is None or target is None:
            findings.append(
                _finding(
                    "DAG_EDGE_NODE_MISSING",
                    "Edge references a missing source or target node.",
                    "Reconnect the edge to existing nodes.",
                    edge_id=edge.id,
                )
            )
            continue
        source_port = next((port for port in source.output_ports if port.id == edge.source_port_id), None)
        target_port = next((port for port in target.input_ports if port.id == edge.target_port_id), None)
        if source_port is None or target_port is None:
            findings.append(
                _finding(
                    "DAG_EDGE_PORT_MISSING",
                    "Edge references a missing source or target port.",
                    "Select ports declared by the registered node types.",
                    edge_id=edge.id,
                )
            )
            continue
        if not _compatible(source_port.artifact_type, target_port.artifact_type):
            findings.append(
                _finding(
                    "DAG_EDGE_PORT_INCOMPATIBLE",
                    f"Cannot connect {source_port.artifact_type} to {target_port.artifact_type}.",
                    "Connect ports with compatible typed artifact contracts.",
                    edge_id=edge.id,
                )
            )
            continue
        incoming_ports[(target.id, target_port.id)] += 1
        if incoming_ports[(target.id, target_port.id)] > 1 and not target_port.multiple:
            findings.append(
                _finding(
                    "DAG_INPUT_CARDINALITY_INVALID",
                    "Multiple edges target a single-value input port.",
                    "Use a collection port or remove the duplicate connection.",
                    edge_id=edge.id,
                )
            )
        valid_edges.append(edge)
    for node in workflow.nodes:
        for port in node.input_ports:
            if port.required and incoming_ports[(node.id, port.id)] == 0:
                findings.append(
                    _finding(
                        "DAG_REQUIRED_INPUT_MISSING",
                        f"Required input {port.id} is not connected.",
                        "Connect a compatible upstream output.",
                        node_id=node.id,
                    )
                )
    for output in workflow.outputs:
        output_node = node_by_id.get(output.node_id)
        if output_node is None or not any(
            port.id == output.port_id and _compatible(port.artifact_type, output.artifact_type)
            for port in output_node.output_ports
        ):
            findings.append(
                _finding(
                    "DAG_REQUIRED_OUTPUT_INVALID",
                    f"Output {output.id} does not reference a compatible node port.",
                    "Select an existing output port with the declared artifact type.",
                )
            )
    if not workflow.outputs:
        findings.append(
            _finding(
                "DAG_OUTPUT_MISSING", "Workflow declares no outputs.", "Declare at least one auditable workflow output."
            )
        )
    unique_node_ids = sorted(node_counts)
    order, reachable, _, indegree = _topological(unique_node_ids, valid_edges)
    if len(order) != len(unique_node_ids):
        findings.append(
            _finding(
                "DAG_CYCLE_DETECTED",
                "The workflow graph contains a cycle.",
                "Remove the circular dependency before execution.",
            )
        )
    start_nodes = [node_id for node_id, count in indegree.items() if count == 0]
    if workflow.multiple_start_policy == "single" and len(start_nodes) != 1:
        findings.append(
            _finding(
                "DAG_START_NODE_POLICY_VIOLATED",
                f"Expected one start node but found {len(start_nodes)}.",
                "Connect independent starts or change the reviewed policy.",
            )
        )
    for node_id in sorted(set(unique_node_ids) - reachable):
        findings.append(
            _finding(
                "DAG_NODE_UNREACHABLE",
                "Node is not reachable from a start node.",
                "Connect or remove the unreachable node.",
                severity=Severity.ERROR,
                node_id=node_id,
            )
        )
    valid = not any(item.severity in {Severity.BLOCKING, Severity.ERROR} for item in findings)
    return DagValidationResult(
        workflow_id=workflow.id,
        workflow_version=workflow.version,
        valid=valid,
        findings=findings,
        topological_order=order if len(order) == len(unique_node_ids) else [],
        reachable_nodes=sorted(reachable),
    )
