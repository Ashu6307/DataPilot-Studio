"""Workspace-scoped DAG adapters for immutable local source handles."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from packages.contracts import DagNode, DiscoveryOverrides
from packages.data_engine.discovery import discover_source, read_selected_table
from packages.workflow_dag.adapters import DagAdapterRegistry, NodeInputs, RuntimeControl, engine_adapter_registry

from .services import DataPilotService


def application_adapter_registry(service: DataPilotService) -> DagAdapterRegistry:
    registry = engine_adapter_registry()

    def source_reference(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
        del inputs
        control.check_cancelled()
        source_id = UUID(str(node.configuration["source_id"]))
        handle, source = service._source(source_id)
        source.assert_unchanged()
        return {
            "source": {
                "source_id": str(handle.id),
                "sha256": handle.sha256,
                "original_filename": handle.original_filename,
            }
        }

    def inspect_source(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
        references = inputs.get("source", [])
        if len(references) != 1 or not isinstance(references[0], dict):
            raise ValueError("DAG_SOURCE_REFERENCE_REQUIRED")
        source_id = UUID(str(references[0]["source_id"]))
        handle, source = service._source(source_id)
        source.assert_unchanged()
        overrides = DiscoveryOverrides.model_validate(node.configuration.get("overrides", {}))
        result = discover_source(source, handle, overrides)
        control.progress(node.id, len(result.tables), len(result.tables), "Source discovery complete")
        return {"discovery": result}

    def select_table(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
        references = inputs.get("source", [])
        if len(references) != 1 or not isinstance(references[0], dict):
            raise ValueError("DAG_SOURCE_REFERENCE_REQUIRED")
        source_id = UUID(str(references[0]["source_id"]))
        _, source = service._source(source_id)
        source.assert_unchanged()
        overrides = DiscoveryOverrides.model_validate(node.configuration.get("overrides", {}))
        table = read_selected_table(source, overrides)
        source.assert_unchanged()
        control.progress(node.id, table.height, table.height, "Selected table loaded")
        return {"dataset": table}

    def saved_dataset(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
        del inputs
        source_id = UUID(str(node.configuration["source_id"]))
        _, source = service._source(source_id)
        source.assert_unchanged()
        overrides = DiscoveryOverrides.model_validate(node.configuration.get("overrides", {}))
        table = read_selected_table(source, overrides)
        source.assert_unchanged()
        control.progress(node.id, table.height, table.height, "Saved canonical dataset loaded")
        return {"dataset": table}

    registry.register("source.excel", source_reference)
    registry.register("source.csv", source_reference)
    registry.register("source.saved_dataset", saved_dataset)
    registry.register("discovery.inspect", inspect_source)
    registry.register("discovery.table_select", select_table)
    return registry
