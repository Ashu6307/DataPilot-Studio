"""Closed Pydantic node-configuration contract dispatch."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from packages.contracts import (
    AggregationConfiguration,
    AppendConfiguration,
    BatchCatalogRequest,
    CalculatedFieldConfiguration,
    ComparisonConfiguration,
    DiscoveryNodeConfiguration,
    EvidencePackageConfiguration,
    EvidenceRegenerationRequest,
    ExportConfiguration,
    ExpressionNode,
    FailConfiguration,
    FolderScanConfiguration,
    JoinConfiguration,
    ManifestConfiguration,
    ManualCheckpointNodeConfiguration,
    MappingSet,
    MergePolicy,
    OperationNode,
    PivotConfiguration,
    ReconciliationWorkflow,
    ReferentialIntegrityConfiguration,
    RuntimeParameterDefinition,
    SavedDatasetReference,
    SchemaExpectation,
    SourceNodeConfiguration,
    SplitConfiguration,
    StopConfiguration,
    SubflowInstanceConfiguration,
    UnpivotConfiguration,
    ValidationNodeConfiguration,
)

CONFIGURATION_MODELS: dict[str, type[BaseModel]] = {
    "AggregationConfiguration": AggregationConfiguration,
    "AppendConfiguration": AppendConfiguration,
    "BatchCatalogRequest": BatchCatalogRequest,
    "CalculatedFieldConfiguration": CalculatedFieldConfiguration,
    "ComparisonConfiguration": ComparisonConfiguration,
    "DiscoveryNodeConfiguration": DiscoveryNodeConfiguration,
    "EvidencePackageConfiguration": EvidencePackageConfiguration,
    "EvidenceRegenerationRequest": EvidenceRegenerationRequest,
    "ExportConfiguration": ExportConfiguration,
    "ExpressionNode": ExpressionNode,
    "FailConfiguration": FailConfiguration,
    "FolderScanConfiguration": FolderScanConfiguration,
    "JoinConfiguration": JoinConfiguration,
    "ManifestConfiguration": ManifestConfiguration,
    "ManualCheckpointNodeConfiguration": ManualCheckpointNodeConfiguration,
    "MappingSet": MappingSet,
    "MergePolicy": MergePolicy,
    "OperationNode": OperationNode,
    "PivotConfiguration": PivotConfiguration,
    "ReconciliationWorkflow": ReconciliationWorkflow,
    "ReferentialIntegrityConfiguration": ReferentialIntegrityConfiguration,
    "RuntimeParameterDefinition": RuntimeParameterDefinition,
    "SavedDatasetReference": SavedDatasetReference,
    "SchemaExpectation": SchemaExpectation,
    "SourceNodeConfiguration": SourceNodeConfiguration,
    "SplitConfiguration": SplitConfiguration,
    "StopConfiguration": StopConfiguration,
    "SubflowInstanceConfiguration": SubflowInstanceConfiguration,
    "UnpivotConfiguration": UnpivotConfiguration,
    "ValidationNodeConfiguration": ValidationNodeConfiguration,
}


def validate_node_configuration(schema_name: str, configuration: dict[str, Any]) -> BaseModel:
    model = CONFIGURATION_MODELS.get(schema_name)
    if model is None:
        raise ValueError(f"DAG_CONFIGURATION_SCHEMA_UNREGISTERED:{schema_name}")
    return model.model_validate(configuration)
