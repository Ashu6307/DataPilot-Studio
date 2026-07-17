"""Generate deterministic anonymised Milestone 3A visual workflow templates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from packages.contracts import (
    DagEdge,
    DagNode,
    DagOutputDefinition,
    DagPosition,
    DagWorkflow,
    ParameterType,
    RuntimeParameterDefinition,
    WorkflowLifecycle,
)
from packages.workflow_dag.registry import default_registry

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "samples" / "dag_templates"
NOW = datetime(2026, 7, 17, tzinfo=UTC)
PROJECT_ID = UUID("30000000-0000-4000-8000-000000000001")
SOURCE_IDS = [UUID(f"31000000-0000-4000-8000-{index:012d}") for index in range(1, 11)]


def node(node_id: str, type_id: str, x: float, configuration: dict[str, Any]) -> DagNode:
    capability = default_registry.require(type_id, 1)
    return DagNode(
        id=node_id,
        node_type_id=type_id,
        display_name=capability.display_name,
        category=capability.category,
        position=DagPosition(x=x, y=180),
        configuration=configuration,
        input_ports=capability.input_ports,
        output_ports=capability.output_ports,
        retry_classification=capability.retry_classification,
        entitlement_capability_id=capability.entitlement_capability_id,
        created_at=NOW,
        updated_at=NOW,
    )


def edge(edge_id: str, source: DagNode, source_port: str, target: DagNode, target_port: str) -> DagEdge:
    source_type = next(port.artifact_type for port in source.output_ports if port.id == source_port)
    return DagEdge(
        id=edge_id,
        source_node_id=source.id,
        source_port_id=source_port,
        target_node_id=target.id,
        target_port_id=target_port,
        data_contract_reference=f"{source_type}/v1",
    )


def workflow(
    workflow_id: int,
    name: str,
    nodes: list[DagNode],
    edges: list[DagEdge],
    output_node: DagNode,
    output_port: str,
    parameters: list[RuntimeParameterDefinition],
) -> DagWorkflow:
    port = next(item for item in output_node.output_ports if item.id == output_port)
    return DagWorkflow(
        id=UUID(f"32000000-0000-4000-8000-{workflow_id:012d}"),
        project_id=PROJECT_ID,
        display_name=name,
        description="Anonymised, configuration-driven Milestone 3A visual workflow template.",
        lifecycle=WorkflowLifecycle.PUBLISHED,
        tags=["template", "anonymised", "milestone-3a"],
        input_parameters=parameters,
        nodes=nodes,
        edges=edges,
        outputs=[
            DagOutputDefinition(
                id="primary_output",
                display_name="Primary evidence output",
                node_id=output_node.id,
                port_id=output_port,
                artifact_type=port.artifact_type,
            )
        ],
        change_note="Published anonymised template version 1",
        created_at=NOW,
        updated_at=NOW,
    )


def source_parameter(identifier: str, label: str, value: UUID) -> RuntimeParameterDefinition:
    return RuntimeParameterDefinition(
        id=identifier,
        label=label,
        data_type=ParameterType.TEXT,
        required=True,
        default_value=str(value),
    )


def templates() -> dict[str, tuple[DagWorkflow, dict[str, Any], str]]:
    clean_source = node("source", "source.saved_dataset", 80, {"source_id": "${parameters.source_id}", "overrides": {}})
    clean = node(
        "trim_identifier",
        "cleaning.operation",
        360,
        {"operation_id": "text.trim", "operation_version": 1, "config": {"field_id": "record_id"}, "enabled": True},
    )
    validate = node("validate", "validation.rules", 650, {"rules": []})
    excel = node("excel_evidence", "output.excel", 930, {"filename_prefix": "clean_validation_evidence"})
    first = workflow(
        1,
        "Generic File Cleaning and Validation",
        [clean_source, clean, validate, excel],
        [
            edge("source_clean", clean_source, "dataset", clean, "dataset"),
            edge("clean_validate", clean, "dataset", validate, "dataset"),
            edge("validate_excel", validate, "dataset", excel, "input"),
        ],
        excel,
        "package",
        [source_parameter("source_id", "Canonical source", SOURCE_IDS[0])],
    )

    monthly_left = node("month_a", "source.saved_dataset", 80, {"source_id": "${parameters.month_a}", "overrides": {}})
    monthly_right = node("month_b", "source.saved_dataset", 80, {"source_id": "${parameters.month_b}", "overrides": {}})
    monthly_right.position.y = 340
    append = node("append_months", "composition.append", 420, {})
    csv_output = node("consolidated_csv", "output.csv", 760, {"filename_prefix": "monthly_consolidated"})
    second = workflow(
        2,
        "Monthly Multi-file Consolidation",
        [monthly_left, monthly_right, append, csv_output],
        [
            edge("month_a_append", monthly_left, "dataset", append, "datasets"),
            edge("month_b_append", monthly_right, "dataset", append, "datasets"),
            edge("append_csv", append, "dataset", csv_output, "input"),
        ],
        csv_output,
        "package",
        [
            source_parameter("month_a", "First monthly file", SOURCE_IDS[1]),
            source_parameter("month_b", "Second monthly file", SOURCE_IDS[2]),
        ],
    )

    comparison_payload = json.loads(
        (ROOT / "samples/profiles/old_new_report_comparison/workflow.json").read_text(encoding="utf-8")
    )["comparison"]
    old = node("old_dataset", "source.saved_dataset", 80, {"source_id": "${parameters.old_source}", "overrides": {}})
    new = node("new_dataset", "source.saved_dataset", 80, {"source_id": "${parameters.new_source}", "overrides": {}})
    new.position.y = 340
    compare = node("compare", "comparison.dataset", 430, comparison_payload)
    comparison_manifest = node(
        "comparison_manifest", "output.json_manifest", 770, {"filename_prefix": "comparison_manifest"}
    )
    third = workflow(
        3,
        "Old vs New Dataset Comparison",
        [old, new, compare, comparison_manifest],
        [
            edge("old_compare", old, "dataset", compare, "left"),
            edge("new_compare", new, "dataset", compare, "right"),
            edge("compare_manifest", compare, "comparison", comparison_manifest, "input"),
        ],
        comparison_manifest,
        "manifest",
        [
            source_parameter("old_source", "Old dataset", SOURCE_IDS[3]),
            source_parameter("new_source", "New dataset", SOURCE_IDS[4]),
        ],
    )

    reconciliation_payload = json.loads(
        (ROOT / "samples/profiles/vendor_invoice_reconciliation/workflow.json").read_text(encoding="utf-8")
    )
    recon_left = node(
        "left_dataset", "source.saved_dataset", 60, {"source_id": "${parameters.left_source}", "overrides": {}}
    )
    recon_right = node(
        "right_dataset", "source.saved_dataset", 60, {"source_id": "${parameters.right_source}", "overrides": {}}
    )
    recon_right.position.y = 340
    reconcile = node("staged_reconciliation", "reconciliation.staged", 390, reconciliation_payload)
    review = node(
        "manual_review",
        "reconciliation.manual_review",
        680,
        {
            "checkpoint_type": "reconciliation_review",
            "reason": "Review ambiguous candidates before evidence publication.",
        },
    )
    package = node(
        "evidence_package",
        "output.zip_evidence",
        980,
        {"filename_prefix": "reconciliation_evidence", "include_manifest": True},
    )
    fourth = workflow(
        4,
        "Staged Reconciliation with Manual Review",
        [recon_left, recon_right, reconcile, review, package],
        [
            edge("left_reconcile", recon_left, "dataset", reconcile, "left"),
            edge("right_reconcile", recon_right, "dataset", reconcile, "right"),
            edge("reconcile_review", reconcile, "result", review, "result"),
            edge("review_result_package", review, "result", package, "input"),
            edge("review_decisions_package", review, "decisions", package, "input"),
        ],
        package,
        "package",
        [
            source_parameter("left_source", "Left canonical dataset", SOURCE_IDS[5]),
            source_parameter("right_source", "Right canonical dataset", SOURCE_IDS[6]),
        ],
    )

    quality_source = node(
        "quality_source", "source.saved_dataset", 70, {"source_id": "${parameters.source_id}", "overrides": {}}
    )
    quality = node("quality_rules", "validation.rules", 360, {"rules": []})
    gate = node(
        "quality_gate",
        "control.manual_approval",
        650,
        {"checkpoint_type": "quality_threshold_approval", "reason": "Approve the quality summary before publication."},
    )
    quality_export = node("quality_evidence", "output.excel", 930, {"filename_prefix": "quality_gate_evidence"})
    fifth = workflow(
        5,
        "Data Quality Gate and Evidence Export",
        [quality_source, quality, gate, quality_export],
        [
            edge("source_quality", quality_source, "dataset", quality, "dataset"),
            edge("quality_gate", quality, "dataset", gate, "input"),
            edge("gate_export", gate, "approved", quality_export, "input"),
        ],
        quality_export,
        "package",
        [source_parameter("source_id", "Quality source", SOURCE_IDS[7])],
    )
    return {
        "generic_file_cleaning_validation": (
            first,
            {"source_id": str(SOURCE_IDS[0])},
            "source → clean → validate → Excel evidence",
        ),
        "monthly_multi_file_consolidation": (
            second,
            {"month_a": str(SOURCE_IDS[1]), "month_b": str(SOURCE_IDS[2])},
            "two sources → append → CSV output",
        ),
        "old_new_dataset_comparison": (
            third,
            {"old_source": str(SOURCE_IDS[3]), "new_source": str(SOURCE_IDS[4])},
            "old/new sources → comparison → JSON manifest",
        ),
        "staged_reconciliation_manual_review": (
            fourth,
            {"left_source": str(SOURCE_IDS[5]), "right_source": str(SOURCE_IDS[6])},
            "two sources → staged matching → manual review → ZIP evidence",
        ),
        "data_quality_gate_evidence": (
            fifth,
            {"source_id": str(SOURCE_IDS[7])},
            "source → quality rules → approval gate → Excel evidence",
        ),
    }


def main() -> None:
    TEMPLATE_ROOT.mkdir(parents=True, exist_ok=True)
    fixture = "record_id,category,amount,event_date\nA-001,alpha,100.00,2026-06-01\nA-002,beta,205.50,2026-06-02\n"
    for slug, (definition, parameters, path) in templates().items():
        directory = TEMPLATE_ROOT / slug
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "workflow.json").write_text(definition.model_dump_json(indent=2), encoding="utf-8")
        (directory / "sample-parameters.json").write_text(json.dumps(parameters, indent=2) + "\n", encoding="utf-8")
        (directory / "input.csv").write_text(fixture, encoding="utf-8")
        (directory / "README.md").write_text(
            f"# {definition.display_name}\n\nAnonymised visual workflow template.\n\n"
            f"Expected execution path: `{path}`.\n\n"
            "UI walkthrough: create a local project, open Visual Workflow Studio, load this template, "
            "bind the sample source parameters, validate, inspect the plan, publish, and run.\n",
            encoding="utf-8",
        )
    print(f"Generated {len(templates())} DAG templates in {TEMPLATE_ROOT}")


if __name__ == "__main__":
    main()
