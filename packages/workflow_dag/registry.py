"""Closed node capability registry that delegates to existing DataPilot engines."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from packages.contracts import (
    ArtifactType,
    DagNode,
    DagPort,
    NodeCapability,
    NodeCategory,
    RetryClassification,
)


class EntitlementProvider(Protocol):
    def has_capability(self, capability_id: str) -> bool: ...


class AllowAllEntitlements:
    """Provider-neutral local development policy; it performs no licensing."""

    def has_capability(self, capability_id: str) -> bool:
        return bool(capability_id)


def _port(
    port_id: str,
    artifact_type: ArtifactType,
    *,
    required: bool = True,
    multiple: bool = False,
) -> DagPort:
    return DagPort(
        id=port_id,
        display_name=port_id.replace("_", " ").title(),
        artifact_type=artifact_type,
        required=required,
        multiple=multiple,
    )


def _capability(
    type_id: str,
    name: str,
    category: NodeCategory,
    inputs: list[DagPort],
    outputs: list[DagPort],
    adapter: str,
    schema: str,
    *,
    preview: bool = True,
    cancellation: bool = True,
    checkpoint: bool = True,
    retry: RetryClassification = RetryClassification.DETERMINISTIC,
) -> NodeCapability:
    return NodeCapability(
        type_id=type_id,
        display_name=name,
        category=category,
        input_ports=inputs,
        output_ports=outputs,
        configuration_schema=schema,
        validation_method="closed_pydantic_contract",
        preview_supported=preview,
        execution_adapter_id=adapter,
        cancellation_supported=cancellation,
        checkpoint_supported=checkpoint,
        retry_classification=retry,
        audit_fields=["node_id", "node_type_id", "node_version", "reason_code", "artifact_fingerprints"],
        entitlement_capability_id=f"workflow.node.{type_id}",
    )


def _initial_capabilities() -> list[NodeCapability]:
    source = ArtifactType.SOURCE_REFERENCE
    dataset = ArtifactType.CANONICAL_DATASET
    datasets = ArtifactType.DATASET_COLLECTION
    control = ArtifactType.CONTROL
    capabilities = [
        _capability(
            "source.excel",
            "Excel source",
            NodeCategory.SOURCE,
            [],
            [_port("source", source)],
            "source.excel",
            "SourceNodeConfiguration",
        ),
        _capability(
            "source.csv",
            "CSV source",
            NodeCategory.SOURCE,
            [],
            [_port("source", source)],
            "source.csv",
            "SourceNodeConfiguration",
        ),
        _capability(
            "source.multi_file",
            "Multi-file source",
            NodeCategory.SOURCE,
            [],
            [_port("sources", ArtifactType.SOURCE_COLLECTION)],
            "source.multi_file",
            "BatchCatalogRequest",
        ),
        _capability(
            "source.folder",
            "Folder source",
            NodeCategory.SOURCE,
            [],
            [_port("sources", ArtifactType.SOURCE_COLLECTION)],
            "source.folder",
            "FolderScanConfiguration",
        ),
        _capability(
            "source.saved_dataset",
            "Saved canonical dataset",
            NodeCategory.SOURCE,
            [],
            [_port("dataset", dataset)],
            "source.saved_dataset",
            "SavedDatasetReference",
        ),
        _capability(
            "discovery.inspect",
            "Source inspection",
            NodeCategory.DISCOVERY,
            [_port("source", source)],
            [_port("discovery", ArtifactType.DISCOVERY)],
            "discovery.inspect",
            "DiscoveryNodeConfiguration",
        ),
        _capability(
            "discovery.table_select",
            "Table selection",
            NodeCategory.DISCOVERY,
            [_port("source", source), _port("discovery", ArtifactType.DISCOVERY)],
            [_port("dataset", dataset)],
            "discovery.table_select",
            "DiscoveryNodeConfiguration",
        ),
        _capability(
            "mapping.canonical",
            "Canonical mapping",
            NodeCategory.DISCOVERY,
            [_port("dataset", dataset)],
            [_port("dataset", dataset)],
            "mapping.canonical",
            "MappingSet",
        ),
        _capability(
            "mapping.schema_drift",
            "Schema-drift review",
            NodeCategory.DISCOVERY,
            [_port("discovery", ArtifactType.DISCOVERY)],
            [_port("decision", control), _port("discovery", ArtifactType.DISCOVERY)],
            "mapping.schema_drift",
            "SchemaExpectation",
            retry=RetryClassification.MANUAL,
        ),
        _capability(
            "cleaning.operation",
            "Cleaning operation",
            NodeCategory.CLEANING,
            [_port("dataset", dataset)],
            [_port("dataset", dataset)],
            "cleaning.operation",
            "OperationNode",
        ),
        _capability(
            "validation.rules",
            "Validation rules",
            NodeCategory.VALIDATION,
            [_port("dataset", dataset)],
            [_port("dataset", dataset), _port("findings", ArtifactType.VALIDATION_FINDINGS)],
            "validation.rules",
            "ValidationNodeConfiguration",
        ),
        _capability(
            "calculation.safe_expression",
            "Calculated field",
            NodeCategory.CALCULATION,
            [_port("dataset", dataset)],
            [_port("dataset", dataset)],
            "calculation.safe_expression",
            "CalculatedFieldConfiguration",
        ),
        _capability(
            "composition.append",
            "Append / union",
            NodeCategory.COMPOSITION,
            [_port("datasets", dataset, multiple=True)],
            [_port("dataset", dataset)],
            "composition.append",
            "AppendConfiguration",
        ),
        _capability(
            "composition.join",
            "Join",
            NodeCategory.COMPOSITION,
            [_port("left", dataset), _port("right", dataset)],
            [_port("dataset", dataset)],
            "composition.join",
            "JoinConfiguration",
        ),
        _capability(
            "composition.aggregate",
            "Group and aggregate",
            NodeCategory.COMPOSITION,
            [_port("dataset", dataset)],
            [_port("dataset", dataset)],
            "composition.aggregate",
            "AggregationConfiguration",
        ),
        _capability(
            "composition.pivot",
            "Pivot",
            NodeCategory.COMPOSITION,
            [_port("dataset", dataset)],
            [_port("dataset", dataset)],
            "composition.pivot",
            "PivotConfiguration",
        ),
        _capability(
            "composition.unpivot",
            "Unpivot",
            NodeCategory.COMPOSITION,
            [_port("dataset", dataset)],
            [_port("dataset", dataset)],
            "composition.unpivot",
            "UnpivotConfiguration",
        ),
        _capability(
            "composition.split",
            "Split",
            NodeCategory.COMPOSITION,
            [_port("dataset", dataset)],
            [_port("datasets", datasets)],
            "composition.split",
            "SplitConfiguration",
        ),
        _capability(
            "comparison.dataset",
            "Dataset comparison",
            NodeCategory.RECONCILIATION,
            [_port("left", dataset), _port("right", dataset)],
            [_port("comparison", ArtifactType.COMPARISON_RESULT)],
            "comparison.dataset",
            "ComparisonConfiguration",
        ),
        _capability(
            "integrity.referential",
            "Referential integrity",
            NodeCategory.RECONCILIATION,
            [_port("parent", dataset), _port("child", dataset)],
            [_port("integrity", ArtifactType.INTEGRITY_RESULT)],
            "integrity.referential",
            "ReferentialIntegrityConfiguration",
        ),
        _capability(
            "reconciliation.staged",
            "Staged reconciliation",
            NodeCategory.RECONCILIATION,
            [_port("left", dataset), _port("right", dataset)],
            [_port("result", ArtifactType.RECONCILIATION_RESULT)],
            "reconciliation.staged",
            "ReconciliationWorkflow",
        ),
        _capability(
            "reconciliation.manual_review",
            "Manual review checkpoint",
            NodeCategory.RECONCILIATION,
            [_port("result", ArtifactType.RECONCILIATION_RESULT)],
            [_port("decisions", ArtifactType.REVIEW_DECISIONS), _port("result", ArtifactType.RECONCILIATION_RESULT)],
            "reconciliation.manual_review",
            "ManualCheckpointNodeConfiguration",
            retry=RetryClassification.MANUAL,
        ),
        _capability(
            "reconciliation.evidence_regenerate",
            "Review-aware evidence regeneration",
            NodeCategory.RECONCILIATION,
            [_port("result", ArtifactType.RECONCILIATION_RESULT), _port("decisions", ArtifactType.REVIEW_DECISIONS)],
            [_port("package", ArtifactType.EVIDENCE_PACKAGE)],
            "reconciliation.evidence_regenerate",
            "EvidenceRegenerationRequest",
        ),
        _capability(
            "output.excel",
            "Excel export",
            NodeCategory.OUTPUT,
            [_port("input", ArtifactType.ANY)],
            [_port("package", ArtifactType.EVIDENCE_PACKAGE)],
            "output.excel",
            "ExportConfiguration",
            preview=False,
        ),
        _capability(
            "output.csv",
            "CSV export",
            NodeCategory.OUTPUT,
            [_port("input", ArtifactType.ANY)],
            [_port("package", ArtifactType.EVIDENCE_PACKAGE)],
            "output.csv",
            "ExportConfiguration",
            preview=False,
        ),
        _capability(
            "output.json_manifest",
            "JSON manifest",
            NodeCategory.OUTPUT,
            [_port("input", ArtifactType.ANY)],
            [_port("manifest", ArtifactType.MANIFEST)],
            "output.json_manifest",
            "ManifestConfiguration",
            preview=False,
        ),
        _capability(
            "output.zip_evidence",
            "ZIP evidence package",
            NodeCategory.OUTPUT,
            [_port("input", ArtifactType.ANY, multiple=True)],
            [_port("package", ArtifactType.EVIDENCE_PACKAGE)],
            "output.zip_evidence",
            "EvidencePackageConfiguration",
            preview=False,
        ),
        _capability(
            "control.condition",
            "Conditional branch",
            NodeCategory.CONTROL,
            [_port("input", ArtifactType.ANY)],
            [_port("true", control), _port("false", control)],
            "control.condition",
            "ExpressionNode",
        ),
        _capability(
            "control.merge",
            "Merge branch",
            NodeCategory.CONTROL,
            [_port("branches", ArtifactType.ANY, multiple=True)],
            [_port("output", ArtifactType.ANY)],
            "control.merge",
            "MergePolicy",
        ),
        _capability(
            "control.manual_approval",
            "Manual approval checkpoint",
            NodeCategory.CONTROL,
            [_port("input", ArtifactType.ANY)],
            [_port("approved", ArtifactType.ANY)],
            "control.manual_approval",
            "ManualCheckpointNodeConfiguration",
            retry=RetryClassification.MANUAL,
        ),
        _capability(
            "control.parameter",
            "Workflow parameter",
            NodeCategory.CONTROL,
            [],
            [_port("value", ArtifactType.ANY)],
            "control.parameter",
            "RuntimeParameterDefinition",
        ),
        _capability(
            "control.stop",
            "Stop workflow",
            NodeCategory.CONTROL,
            [_port("control", control, required=False)],
            [],
            "control.stop",
            "StopConfiguration",
            preview=False,
            retry=RetryClassification.NEVER,
        ),
        _capability(
            "control.fail",
            "Fail workflow",
            NodeCategory.CONTROL,
            [_port("control", control, required=False)],
            [],
            "control.fail",
            "FailConfiguration",
            preview=False,
            retry=RetryClassification.NEVER,
        ),
        _capability(
            "subflow.reference",
            "Reusable subflow",
            NodeCategory.SUBFLOW,
            [_port("input", ArtifactType.ANY, required=False, multiple=True)],
            [_port("output", ArtifactType.ANY, required=False, multiple=True)],
            "subflow.reference",
            "SubflowInstanceConfiguration",
        ),
    ]
    return capabilities


class NodeCapabilityRegistry:
    def __init__(self, capabilities: Iterable[NodeCapability] = ()) -> None:
        self._capabilities: dict[tuple[str, int], NodeCapability] = {}
        for capability in capabilities:
            self.register(capability)

    def register(self, capability: NodeCapability) -> None:
        key = (capability.type_id, capability.version)
        if key in self._capabilities:
            raise ValueError(f"NODE_CAPABILITY_DUPLICATE:{capability.type_id}:{capability.version}")
        self._capabilities[key] = capability

    def get(self, type_id: str, version: int) -> NodeCapability | None:
        return self._capabilities.get((type_id, version))

    def require(self, type_id: str, version: int) -> NodeCapability:
        capability = self.get(type_id, version)
        if capability is None:
            raise ValueError(f"NODE_CAPABILITY_UNSUPPORTED:{type_id}:{version}")
        return capability

    def list_capabilities(self) -> list[NodeCapability]:
        return sorted(self._capabilities.values(), key=lambda item: (item.category, item.display_name))

    def instantiate(self, node: DagNode) -> DagNode:
        capability = self.require(node.node_type_id, node.node_version)
        return node.model_copy(
            update={
                "category": capability.category,
                "input_ports": capability.input_ports,
                "output_ports": capability.output_ports,
                "retry_classification": capability.retry_classification,
                "entitlement_capability_id": capability.entitlement_capability_id,
            }
        )


default_registry = NodeCapabilityRegistry(_initial_capabilities())
