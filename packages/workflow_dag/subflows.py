"""Version-pinned subflow dependency validation and bounded expansion."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from uuid import UUID

from packages.contracts import DagEdge, DagNode, DagWorkflow, SubflowDefinition

SubflowKey = tuple[UUID, int]


def validate_subflow_dependencies(
    root: SubflowKey,
    definitions: Mapping[SubflowKey, SubflowDefinition],
    maximum_depth: int,
) -> None:
    """Reject missing, recursive, or excessively deep pinned dependencies."""

    visiting: set[SubflowKey] = set()
    visited: set[SubflowKey] = set()

    def visit(key: SubflowKey, depth: int) -> None:
        if depth > maximum_depth:
            raise ValueError("DAG_SUBFLOW_DEPTH_LIMIT_EXCEEDED")
        if key in visiting:
            raise ValueError("DAG_SUBFLOW_RECURSION_DETECTED")
        if key in visited:
            return
        definition = definitions.get(key)
        if definition is None:
            raise ValueError(f"DAG_SUBFLOW_VERSION_MISSING:{key[0]}:{key[1]}")
        visiting.add(key)
        for dependency in definition.dependencies:
            visit(dependency, depth + 1)
        visiting.remove(key)
        visited.add(key)

    visit(root, 0)


def _subflow_key(node: DagNode) -> SubflowKey:
    try:
        return UUID(str(node.configuration["subflow_id"])), int(node.configuration["subflow_version"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"DAG_SUBFLOW_CONFIGURATION_INVALID:{node.id}") from error


def expand_subflows(
    workflow: DagWorkflow,
    definitions: Mapping[SubflowKey, SubflowDefinition],
) -> DagWorkflow:
    """Flatten subflow nodes while preserving stable namespaced lineage IDs.

    A subflow node declares ``input_bindings`` and ``output_bindings`` maps in
    its configuration. Each public port maps to ``internal_node.internal_port``.
    The expanded workflow remains an ordinary typed DAG and is revalidated by
    the planner before execution.
    """

    expanded = workflow.model_copy(deep=True)
    for node in list(expanded.nodes):
        if node.node_type_id != "subflow.reference":
            continue
        key = _subflow_key(node)
        validate_subflow_dependencies(key, definitions, expanded.resource_policy.maximum_subflow_depth)
        definition = definitions[key]
        input_bindings = node.configuration.get("input_bindings", {})
        output_bindings = node.configuration.get("output_bindings", {})
        if not isinstance(input_bindings, dict) or not isinstance(output_bindings, dict):
            raise ValueError(f"DAG_SUBFLOW_BINDINGS_INVALID:{node.id}")
        prefix = f"{node.id}."
        internal_nodes: list[DagNode] = []
        for child in definition.nodes:
            copied = deepcopy(child)
            copied.id = f"{prefix}{child.id}"
            copied.display_name = f"{node.display_name} / {child.display_name}"
            internal_nodes.append(copied)
        internal_edges: list[DagEdge] = []
        for edge in definition.edges:
            copied_edge = deepcopy(edge)
            copied_edge.id = f"{prefix}{edge.id}"
            copied_edge.source_node_id = f"{prefix}{edge.source_node_id}"
            copied_edge.target_node_id = f"{prefix}{edge.target_node_id}"
            internal_edges.append(copied_edge)
        rewritten_edges: list[DagEdge] = []
        for edge in expanded.edges:
            copied_edge = deepcopy(edge)
            if edge.target_node_id == node.id:
                binding = input_bindings.get(edge.target_port_id)
                if not isinstance(binding, str) or "." not in binding:
                    raise ValueError(f"DAG_SUBFLOW_INPUT_BINDING_MISSING:{node.id}:{edge.target_port_id}")
                child_id, child_port = binding.rsplit(".", 1)
                copied_edge.target_node_id = f"{prefix}{child_id}"
                copied_edge.target_port_id = child_port
            if edge.source_node_id == node.id:
                binding = output_bindings.get(edge.source_port_id)
                if not isinstance(binding, str) or "." not in binding:
                    raise ValueError(f"DAG_SUBFLOW_OUTPUT_BINDING_MISSING:{node.id}:{edge.source_port_id}")
                child_id, child_port = binding.rsplit(".", 1)
                copied_edge.source_node_id = f"{prefix}{child_id}"
                copied_edge.source_port_id = child_port
            rewritten_edges.append(copied_edge)
        expanded.nodes = [item for item in expanded.nodes if item.id != node.id] + internal_nodes
        expanded.edges = rewritten_edges + internal_edges
        for output in expanded.outputs:
            if output.node_id == node.id:
                binding = output_bindings.get(output.port_id)
                if not isinstance(binding, str) or "." not in binding:
                    raise ValueError(f"DAG_SUBFLOW_OUTPUT_BINDING_MISSING:{node.id}:{output.port_id}")
                child_id, child_port = binding.rsplit(".", 1)
                output.node_id = f"{prefix}{child_id}"
                output.port_id = child_port
    if any(node.node_type_id == "subflow.reference" for node in expanded.nodes):
        return expand_subflows(expanded, definitions)
    return expanded
