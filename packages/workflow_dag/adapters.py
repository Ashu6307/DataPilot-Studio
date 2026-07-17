"""Closed runtime adapters that delegate node work to existing data engines."""

from __future__ import annotations

import csv
import json
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import polars as pl
import xlsxwriter
from pydantic import BaseModel, TypeAdapter

from packages.contracts import (
    AggregationConfiguration,
    AppendConfiguration,
    CalculatedFieldConfiguration,
    CanonicalType,
    ComparisonConfiguration,
    DagNode,
    ExpressionNode,
    JoinConfiguration,
    MappingSet,
    OperationNode,
    PivotConfiguration,
    ReconciliationWorkflow,
    ReferentialIntegrityConfiguration,
    UnpivotConfiguration,
    ValidationRule,
)
from packages.data_engine.batch_exporter import safe_output_name, safe_sheet_name
from packages.data_engine.comparison import compare_datasets
from packages.data_engine.composition import (
    aggregate_table,
    append_tables,
    join_tables,
    pivot_table,
    unpivot_table,
)
from packages.data_engine.expressions import EvaluationContext, apply_calculation, evaluate_expression
from packages.data_engine.mapping import apply_mapping
from packages.data_engine.operations import apply_operation
from packages.data_engine.reconciliation import reconcile_datasets
from packages.data_engine.referential_integrity import check_referential_integrity
from packages.data_engine.validation import validate_table

NodeInputs = Mapping[str, list[Any]]


class RuntimeControl(Protocol):
    def check_cancelled(self) -> None: ...
    def progress(self, node_id: str, rows_processed: int, estimated_rows: int | None, message: str) -> None: ...
    def output_directory(self, node_id: str) -> Path: ...


NodeExecutionAdapter = Callable[[DagNode, NodeInputs, RuntimeControl], dict[str, Any]]


def _one(inputs: NodeInputs, port: str, expected: type[Any] | None = None) -> Any:
    values = inputs.get(port, [])
    if len(values) != 1:
        raise ValueError(f"DAG_RUNTIME_INPUT_CARDINALITY:{port}:{len(values)}")
    value = values[0]
    if expected is not None and not isinstance(value, expected):
        raise TypeError(f"DAG_RUNTIME_INPUT_TYPE:{port}:{expected.__name__}")
    return value


def _many(inputs: NodeInputs, port: str, expected: type[Any] | None = None) -> list[Any]:
    values = list(inputs.get(port, []))
    if expected is not None and any(not isinstance(value, expected) for value in values):
        raise TypeError(f"DAG_RUNTIME_INPUT_TYPE:{port}:{expected.__name__}")
    return values


def _clean(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    table = _one(inputs, "dataset", pl.DataFrame)
    control.check_cancelled()
    result = apply_operation(table, OperationNode.model_validate(node.configuration))
    control.progress(node.id, result.table.height, table.height, "Cleaning operation complete")
    return {"dataset": result.table}


def _validate(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    table = _one(inputs, "dataset", pl.DataFrame)
    rules = TypeAdapter(list[ValidationRule]).validate_python(node.configuration.get("rules", []))
    control.check_cancelled()
    findings = validate_table(table, rules)
    control.progress(node.id, table.height, table.height, "Validation rules complete")
    return {"dataset": table, "findings": findings}


def _calculate(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    table = _one(inputs, "dataset", pl.DataFrame)
    control.check_cancelled()
    field_types: dict[str, CanonicalType] = {}
    for field_name, data_type in table.schema.items():
        if data_type.is_integer():
            field_types[field_name] = CanonicalType.INTEGER
        elif data_type.is_float() or data_type == pl.Decimal:
            field_types[field_name] = CanonicalType.DECIMAL
        elif data_type == pl.Boolean:
            field_types[field_name] = CanonicalType.BOOLEAN
        elif data_type == pl.Date:
            field_types[field_name] = CanonicalType.DATE
        elif data_type == pl.Datetime:
            field_types[field_name] = CanonicalType.DATETIME
        else:
            field_types[field_name] = CanonicalType.TEXT
    output, _ = apply_calculation(
        table,
        CalculatedFieldConfiguration.model_validate(node.configuration),
        field_types,
        node.updated_at.date(),
    )
    control.progress(node.id, output.height, table.height, "Calculated field complete")
    return {"dataset": output}


def _map(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    table = _one(inputs, "dataset", pl.DataFrame)
    control.check_cancelled()
    output = apply_mapping(table, MappingSet.model_validate(node.configuration))
    control.progress(node.id, output.height, table.height, "Canonical mapping complete")
    return {"dataset": output}


def _append(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    tables = _many(inputs, "datasets", pl.DataFrame)
    control.check_cancelled()
    result = append_tables(tables, AppendConfiguration.model_validate(node.configuration))
    control.progress(node.id, result.table.height, result.input_rows, "Append complete")
    return {"dataset": result.table}


def _join(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    left = _one(inputs, "left", pl.DataFrame)
    right = _one(inputs, "right", pl.DataFrame)
    control.check_cancelled()
    result = join_tables(left, right, JoinConfiguration.model_validate(node.configuration))
    control.progress(node.id, result.table.height, left.height + right.height, "Join complete")
    return {"dataset": result.table}


def _aggregate(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    table = _one(inputs, "dataset", pl.DataFrame)
    result = aggregate_table(table, AggregationConfiguration.model_validate(node.configuration))
    control.progress(node.id, result.table.height, table.height, "Aggregation complete")
    return {"dataset": result.table}


def _pivot(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    table = _one(inputs, "dataset", pl.DataFrame)
    result = pivot_table(table, PivotConfiguration.model_validate(node.configuration))
    control.progress(node.id, result.table.height, table.height, "Pivot complete")
    return {"dataset": result.table}


def _unpivot(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    table = _one(inputs, "dataset", pl.DataFrame)
    result = unpivot_table(table, UnpivotConfiguration.model_validate(node.configuration))
    control.progress(node.id, result.table.height, table.height, "Unpivot complete")
    return {"dataset": result.table}


def _compare(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    control.check_cancelled()
    result = compare_datasets(
        _one(inputs, "left", pl.DataFrame),
        _one(inputs, "right", pl.DataFrame),
        ComparisonConfiguration.model_validate(node.configuration),
    )
    return {"comparison": result}


def _integrity(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    control.check_cancelled()
    result = check_referential_integrity(
        _one(inputs, "parent", pl.DataFrame),
        _one(inputs, "child", pl.DataFrame),
        ReferentialIntegrityConfiguration.model_validate(node.configuration),
    )
    return {"integrity": result}


def _reconcile(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    left = _one(inputs, "left", pl.DataFrame)
    right = _one(inputs, "right", pl.DataFrame)
    result = reconcile_datasets(
        left,
        right,
        ReconciliationWorkflow.model_validate(node.configuration),
        cancel=control.check_cancelled,
        progress=lambda stage, rows, total, message: control.progress(node.id, rows, total, f"{stage}: {message}"),
    )
    return {"result": result}


def _merge(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    del control
    branches = _many(inputs, "branches")
    if not branches:
        raise ValueError("DAG_RUNTIME_MERGE_EMPTY")
    if node.configuration.get("strategy") == "require_all" and len(branches) < 2:
        raise ValueError("DAG_RUNTIME_MERGE_BRANCH_MISSING")
    return {"output": branches[0]}


def _condition(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    control.check_cancelled()
    value = _one(inputs, "input")
    row = value.row(0, named=True) if isinstance(value, pl.DataFrame) and value.height else {}
    expression = ExpressionNode.model_validate(node.configuration)
    result = evaluate_expression(
        expression,
        EvaluationContext(row=row, field_types={}, execution_date=node.updated_at.date()),
    )
    if not isinstance(result, bool):
        raise ValueError("DAG_CONDITION_RESULT_NOT_BOOLEAN")
    return {"true" if result else "false": result}


def _parameter(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    del inputs
    control.check_cancelled()
    return {"value": node.configuration.get("default_value")}


def _stop(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    del inputs
    control.check_cancelled()
    raise RuntimeError(str(node.configuration.get("reason", "DAG_CONFIGURED_STOP")))


def _fail(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    del inputs
    control.check_cancelled()
    raise RuntimeError(
        f"{node.configuration.get('reason_code', 'DAG_CONFIGURED_FAILURE')}:"
        f"{node.configuration.get('message', 'Configured failure')}"
    )


def _safe_cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        value = json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pl.DataFrame):
        return value.to_dicts()
    if isinstance(value, BaseModel):
        return [value.model_dump(mode="json")]
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item if isinstance(item, dict) else {"value": item} for item in value]
    return [{"value": value}]


def _excel_output(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    value = _one(inputs, "input")
    rows = _rows(value)
    directory = control.output_directory(node.id)
    path = directory / f"{safe_output_name(str(node.configuration.get('filename_prefix', node.id)))}.xlsx"
    workbook = xlsxwriter.Workbook(path, {"constant_memory": True, "strings_to_formulas": False})
    worksheet = workbook.add_worksheet(safe_sheet_name(node.display_name))
    headers = sorted({key for row in rows for key in row}) or ["status"]
    header_format = workbook.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#17324D"})
    try:
        for column, header in enumerate(headers):
            worksheet.write(0, column, header, header_format)
        for row_index, row in enumerate(rows, start=1):
            for column, header in enumerate(headers):
                worksheet.write(row_index, column, _safe_cell(row.get(header)))
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, max(1, len(rows)), len(headers) - 1)
    finally:
        workbook.close()
    return {"package": path}


def _csv_output(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    rows = _rows(_one(inputs, "input"))
    directory = control.output_directory(node.id)
    path = directory / f"{safe_output_name(str(node.configuration.get('filename_prefix', node.id)))}.csv"
    headers = sorted({key for row in rows for key in row}) or ["status"]
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: _safe_cell(row.get(header)) for header in headers})
    return {"package": path}


def _json_output(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    value = _one(inputs, "input")
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    directory = control.output_directory(node.id)
    path = directory / f"{safe_output_name(str(node.configuration.get('filename_prefix', node.id)))}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return {"manifest": path}


def _zip_output(node: DagNode, inputs: NodeInputs, control: RuntimeControl) -> dict[str, Any]:
    values = _many(inputs, "input")
    directory = control.output_directory(node.id)
    path = directory / f"{safe_output_name(str(node.configuration.get('filename_prefix', node.id)))}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for index, value in enumerate(values):
            name = f"artifact-{index + 1}.json"
            if isinstance(value, Path) and value.is_file():
                name = safe_output_name(value.name)
                content = value.read_bytes()
            else:
                payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
                content = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            package.writestr(info, content)
    return {"package": path}


@dataclass(slots=True)
class DagAdapterRegistry:
    _adapters: dict[str, NodeExecutionAdapter]

    def __init__(self) -> None:
        self._adapters = {}

    def register(self, adapter_id: str, adapter: NodeExecutionAdapter) -> None:
        if adapter_id in self._adapters:
            raise ValueError(f"DAG_ADAPTER_DUPLICATE:{adapter_id}")
        self._adapters[adapter_id] = adapter

    def require(self, adapter_id: str) -> NodeExecutionAdapter:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            raise ValueError(f"DAG_ADAPTER_UNAVAILABLE:{adapter_id}")
        return adapter

    def ids(self) -> list[str]:
        return sorted(self._adapters)


def engine_adapter_registry() -> DagAdapterRegistry:
    registry = DagAdapterRegistry()
    adapters: dict[str, NodeExecutionAdapter] = {
        "cleaning.operation": _clean,
        "validation.rules": _validate,
        "calculation.safe_expression": _calculate,
        "mapping.canonical": _map,
        "composition.append": _append,
        "composition.join": _join,
        "composition.aggregate": _aggregate,
        "composition.pivot": _pivot,
        "composition.unpivot": _unpivot,
        "comparison.dataset": _compare,
        "integrity.referential": _integrity,
        "reconciliation.staged": _reconcile,
        "control.merge": _merge,
        "control.condition": _condition,
        "control.parameter": _parameter,
        "control.stop": _stop,
        "control.fail": _fail,
        "output.excel": _excel_output,
        "output.csv": _csv_output,
        "output.json_manifest": _json_output,
        "output.zip_evidence": _zip_output,
    }
    for adapter_id, adapter in adapters.items():
        registry.register(adapter_id, adapter)
    return registry


def register_callable_adapter(
    registry: DagAdapterRegistry,
    adapter_id: str,
    adapter: Callable[[DagNode, NodeInputs, RuntimeControl], dict[str, Any]],
) -> None:
    """Register an application-owned source/output adapter without dynamic loading."""

    registry.register(adapter_id, adapter)
