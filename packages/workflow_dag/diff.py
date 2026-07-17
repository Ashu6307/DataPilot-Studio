"""Human-reviewable workflow version differences."""

from __future__ import annotations

from typing import Any, Literal

from packages.contracts import DagWorkflow, WorkflowDiff, WorkflowDiffItem

DiffCategory = Literal[
    "node_added",
    "node_removed",
    "node_changed",
    "edge_added",
    "edge_removed",
    "parameter_changed",
    "subflow_version_changed",
    "output_changed",
    "resource_policy_changed",
]


def _json(value: Any) -> Any:
    return value.model_dump(mode="json", exclude={"created_at", "updated_at"})


def _append_map_diff(
    items: list[WorkflowDiffItem],
    before: dict[str, Any],
    after: dict[str, Any],
    added: DiffCategory,
    removed: DiffCategory,
    changed: DiffCategory,
) -> None:
    for object_id in sorted(set(before) | set(after)):
        old = before.get(object_id)
        new = after.get(object_id)
        if old is None:
            items.append(WorkflowDiffItem(category=added, object_id=object_id, after=new))
        elif new is None:
            items.append(WorkflowDiffItem(category=removed, object_id=object_id, before=old))
        elif old != new:
            items.append(WorkflowDiffItem(category=changed, object_id=object_id, before=old, after=new))


def diff_workflows(before: DagWorkflow, after: DagWorkflow) -> WorkflowDiff:
    if before.id != after.id:
        raise ValueError("DAG_DIFF_WORKFLOW_ID_MISMATCH")
    if after.version <= before.version:
        raise ValueError("DAG_DIFF_VERSION_ORDER_INVALID")
    items: list[WorkflowDiffItem] = []
    old_nodes = {node.id: _json(node) for node in before.nodes}
    new_nodes = {node.id: _json(node) for node in after.nodes}
    _append_map_diff(items, old_nodes, new_nodes, "node_added", "node_removed", "node_changed")
    old_edges = {edge.id: _json(edge) for edge in before.edges}
    new_edges = {edge.id: _json(edge) for edge in after.edges}
    _append_map_diff(items, old_edges, new_edges, "edge_added", "edge_removed", "node_changed")
    old_parameters = {parameter.id: _json(parameter) for parameter in before.input_parameters}
    new_parameters = {parameter.id: _json(parameter) for parameter in after.input_parameters}
    for parameter_id in sorted(set(old_parameters) | set(new_parameters)):
        old = old_parameters.get(parameter_id)
        new = new_parameters.get(parameter_id)
        if old != new:
            items.append(WorkflowDiffItem(category="parameter_changed", object_id=parameter_id, before=old, after=new))
    old_outputs = {output.id: _json(output) for output in before.outputs}
    new_outputs = {output.id: _json(output) for output in after.outputs}
    for output_id in sorted(set(old_outputs) | set(new_outputs)):
        old = old_outputs.get(output_id)
        new = new_outputs.get(output_id)
        if old != new:
            items.append(WorkflowDiffItem(category="output_changed", object_id=output_id, before=old, after=new))
    old_resources = before.resource_policy.model_dump(mode="json")
    new_resources = after.resource_policy.model_dump(mode="json")
    if old_resources != new_resources:
        items.append(
            WorkflowDiffItem(
                category="resource_policy_changed",
                object_id="resource_policy",
                before=old_resources,
                after=new_resources,
            )
        )
    incompatible_categories = {"node_removed", "edge_removed", "parameter_changed", "output_changed"}
    compatible = not any(item.category in incompatible_categories for item in items)
    return WorkflowDiff(
        workflow_id=before.id,
        from_version=before.version,
        to_version=after.version,
        compatible=compatible,
        items=items,
    )
