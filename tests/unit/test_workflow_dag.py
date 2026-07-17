from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from packages.contracts import (
    ArtifactType,
    DagEdge,
    DagNode,
    DagOutputDefinition,
    DagPosition,
    DagWorkflow,
    ParameterType,
    RuntimeParameterDefinition,
    RuntimeParameterValue,
    SubflowDefinition,
)
from packages.workflow_dag import (
    build_execution_plan,
    default_registry,
    diff_workflows,
    resolve_runtime_parameters,
    validate_dag,
    validate_subflow_dependencies,
)


def _node(node_id: str, type_id: str, x: float = 0) -> DagNode:
    capability = default_registry.require(type_id, 1)
    now = datetime.now(UTC)
    configuration = {}
    if type_id == "source.saved_dataset":
        configuration = {"source_id": str(uuid4())}
    elif type_id == "cleaning.operation":
        configuration = {"operation_id": "text.trim", "config": {"field_id": "name"}}
    return DagNode(
        id=node_id,
        node_type_id=type_id,
        node_version=1,
        display_name=node_id.replace("_", " ").title(),
        category=capability.category,
        position=DagPosition(x=x, y=0),
        configuration=configuration,
        input_ports=capability.input_ports,
        output_ports=capability.output_ports,
        entitlement_capability_id=capability.entitlement_capability_id,
        created_at=now,
        updated_at=now,
    )


def _workflow() -> DagWorkflow:
    source = _node("source", "source.saved_dataset")
    cleaning = _node("clean", "cleaning.operation", 300)
    return DagWorkflow(
        project_id=uuid4(),
        display_name="Reusable typed workflow",
        nodes=[source, cleaning],
        edges=[
            DagEdge(
                id="source_to_clean",
                source_node_id="source",
                source_port_id="dataset",
                target_node_id="clean",
                target_port_id="dataset",
                data_contract_reference="canonical-dataset/v1",
            )
        ],
        outputs=[
            DagOutputDefinition(
                id="cleaned",
                display_name="Cleaned dataset",
                node_id="clean",
                port_id="dataset",
                artifact_type=ArtifactType.CANONICAL_DATASET,
            )
        ],
    )


def test_registry_exposes_versioned_required_categories() -> None:
    capabilities = default_registry.list_capabilities()
    assert len(capabilities) >= 30
    assert {item.type_id for item in capabilities} >= {
        "source.excel",
        "discovery.inspect",
        "cleaning.operation",
        "validation.rules",
        "composition.join",
        "comparison.dataset",
        "reconciliation.staged",
        "control.condition",
        "control.manual_approval",
        "subflow.reference",
    }
    assert all(item.version >= 1 and item.execution_adapter_id for item in capabilities)


def test_valid_dag_plans_deterministically_without_row_keys() -> None:
    workflow = _workflow()
    result = validate_dag(workflow)
    assert result.valid
    assert result.topological_order == ["source", "clean"]

    first = build_execution_plan(workflow)
    second = build_execution_plan(workflow)
    assert first.plan_fingerprint == second.plan_fingerprint
    assert first.parameter_fingerprint == second.parameter_fingerprint
    assert [node.parallel_group for node in first.nodes] == [1, 2]
    assert first.estimated_sources == 1
    assert first.estimated_outputs == 1


def test_cycle_and_missing_required_input_block_execution() -> None:
    left = _node("left", "control.merge")
    right = _node("right", "control.merge")
    workflow = DagWorkflow(
        project_id=uuid4(),
        display_name="Invalid cycle",
        nodes=[left, right],
        edges=[
            DagEdge(
                id="left_right",
                source_node_id="left",
                source_port_id="output",
                target_node_id="right",
                target_port_id="branches",
                data_contract_reference="any/v1",
            ),
            DagEdge(
                id="right_left",
                source_node_id="right",
                source_port_id="output",
                target_node_id="left",
                target_port_id="branches",
                data_contract_reference="any/v1",
            ),
        ],
        outputs=[
            DagOutputDefinition(
                id="result",
                display_name="Result",
                node_id="right",
                port_id="output",
                artifact_type=ArtifactType.ANY,
            )
        ],
    )
    result = validate_dag(workflow)
    assert not result.valid
    codes = {item.reason_code for item in result.findings}
    assert "DAG_CYCLE_DETECTED" in codes
    assert "DAG_NODE_UNREACHABLE" in codes
    with pytest.raises(ValueError, match="DAG_VALIDATION_FAILED"):
        build_execution_plan(workflow)


def test_parameters_are_typed_bounded_and_secret_safe() -> None:
    workflow = _workflow()
    definitions = [
        RuntimeParameterDefinition(
            id="batch_size",
            label="Batch size",
            data_type=ParameterType.INTEGER,
            required=True,
        ),
        RuntimeParameterDefinition(
            id="credential",
            label="Credential",
            data_type=ParameterType.CREDENTIAL_REFERENCE,
            secret=True,
        ),
    ]
    resolved, audit = resolve_runtime_parameters(
        definitions,
        [
            RuntimeParameterValue(parameter_id="batch_size", value="25"),
            RuntimeParameterValue(parameter_id="credential", value="credential://local/source-a"),
        ],
        workflow.resource_policy,
    )
    assert resolved["batch_size"] == 25
    assert resolved["credential"] == "credential://local/source-a"
    assert audit["credential"] == "[SENSITIVE_REFERENCE]"
    with pytest.raises(ValueError, match="opaque credential"):
        resolve_runtime_parameters(
            definitions,
            [
                RuntimeParameterValue(parameter_id="batch_size", value=25),
                RuntimeParameterValue(parameter_id="credential", value="plain-secret"),
            ],
            workflow.resource_policy,
        )


def test_workflow_diff_marks_removed_contract_as_incompatible() -> None:
    before = _workflow()
    after = before.model_copy(deep=True)
    after.version = 2
    after.nodes = [after.nodes[0]]
    after.edges = []
    after.outputs = [
        DagOutputDefinition(
            id="source_output",
            display_name="Source output",
            node_id="source",
            port_id="dataset",
            artifact_type=ArtifactType.CANONICAL_DATASET,
        )
    ]
    difference = diff_workflows(before, after)
    assert not difference.compatible
    assert {item.category for item in difference.items} >= {"node_removed", "edge_removed", "output_changed"}


def test_subflow_dependency_recursion_and_depth_are_rejected() -> None:
    project_id = uuid4()
    first_id = uuid4()
    second_id = uuid4()
    first = SubflowDefinition(
        id=first_id,
        project_id=project_id,
        display_name="First",
        public_input_ports=[],
        public_output_ports=[],
        nodes=[],
        edges=[],
        dependencies=[(second_id, 1)],
    )
    second = SubflowDefinition(
        id=second_id,
        project_id=project_id,
        display_name="Second",
        public_input_ports=[],
        public_output_ports=[],
        nodes=[],
        edges=[],
        dependencies=[(first_id, 1)],
    )
    definitions = {(first.id, first.version): first, (second.id, second.version): second}
    with pytest.raises(ValueError, match="DAG_SUBFLOW_RECURSION_DETECTED"):
        validate_subflow_dependencies((first.id, first.version), definitions, 5)
    second.dependencies = []
    with pytest.raises(ValueError, match="DAG_SUBFLOW_DEPTH_LIMIT_EXCEEDED"):
        validate_subflow_dependencies((first.id, first.version), definitions, 0)


def test_missing_node_incompatible_port_unsupported_version_and_limits_are_actionable() -> None:
    workflow = _workflow()
    workflow.edges.append(
        DagEdge(
            id="missing_target",
            source_node_id="source",
            source_port_id="dataset",
            target_node_id="missing",
            target_port_id="dataset",
            data_contract_reference="canonical-dataset/v1",
        )
    )
    workflow.nodes[0].node_version = 99
    workflow.resource_policy.maximum_nodes = 1
    result = validate_dag(workflow)
    codes = {item.reason_code for item in result.findings}
    assert {"DAG_EDGE_NODE_MISSING", "DAG_NODE_VERSION_UNSUPPORTED", "DAG_NODE_LIMIT_EXCEEDED"} <= codes

    raw_source = _node("raw_source", "source.excel")
    raw_source.configuration = {"source_id": str(uuid4())}
    clean = _node("clean", "cleaning.operation")
    incompatible = DagWorkflow(
        project_id=uuid4(),
        display_name="Incompatible ports",
        nodes=[raw_source, clean],
        edges=[
            DagEdge(
                id="raw_clean",
                source_node_id="raw_source",
                source_port_id="source",
                target_node_id="clean",
                target_port_id="dataset",
                data_contract_reference="source-reference/v1",
            )
        ],
        outputs=[
            DagOutputDefinition(
                id="result",
                display_name="Result",
                node_id="clean",
                port_id="dataset",
                artifact_type=ArtifactType.CANONICAL_DATASET,
            )
        ],
    )
    assert "DAG_EDGE_PORT_INCOMPATIBLE" in {item.reason_code for item in validate_dag(incompatible).findings}
