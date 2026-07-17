"""Versioned deterministic cleaning operation registry."""

from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import polars as pl

from packages.contracts import OperationMetric, OperationNode
from packages.shared_utils import slugify_field


@dataclass(slots=True)
class OperationResult:
    table: pl.DataFrame
    metric: OperationMetric
    filtered_rows: int = 0


TextTransform = Callable[[str], str | None]


def _required_field(config: dict[str, Any]) -> str:
    field = config.get("field_id")
    if not isinstance(field, str) or not field:
        raise ValueError("operation config requires field_id")
    return field


def _transform_field(table: pl.DataFrame, field: str, transform: TextTransform) -> tuple[pl.DataFrame, int]:
    if field not in table.columns:
        raise ValueError(f"OPERATION_FIELD_NOT_FOUND: {field}")
    before = table.get_column(field).to_list()
    after = [transform("" if value is None else str(value)) for value in before]
    affected = sum(left != right for left, right in zip(before, after, strict=True))
    return table.with_columns(pl.Series(field, after, dtype=pl.String)), affected


def _apply_text(table: pl.DataFrame, node: OperationNode, transform: TextTransform) -> tuple[pl.DataFrame, int, int]:
    result, affected = _transform_field(table, _required_field(node.config), transform)
    return result, affected, 0


def _trim(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    return _apply_text(table, node, lambda value: value.strip())


def _normalise_spaces(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    return _apply_text(table, node, lambda value: re.sub(r"\s+", " ", value).strip())


def _uppercase(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    return _apply_text(table, node, str.upper)


def _lowercase(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    return _apply_text(table, node, str.lower)


def _proper_case(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    return _apply_text(table, node, str.title)


def _remove_non_printable(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    def clean(value: str) -> str:
        return "".join(char for char in value if unicodedata.category(char)[0] != "C" or char in "\t\n")

    return _apply_text(table, node, clean)


def _normalise_nulls(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    configured = node.config.get("null_like_values", ["", "null", "none", "n/a", "na", "-"])
    if not isinstance(configured, list) or not all(isinstance(value, str) for value in configured):
        raise ValueError("null_like_values must be a list of strings")
    nulls = {value.casefold() for value in configured}
    return _apply_text(table, node, lambda value: None if value.strip().casefold() in nulls else value)


def _rename_field(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    field = _required_field(node.config)
    target = node.config.get("new_field_id")
    if not isinstance(target, str) or slugify_field(target) != target:
        raise ValueError("new_field_id must be a canonical snake_case identifier")
    if field not in table.columns:
        raise ValueError(f"OPERATION_FIELD_NOT_FOUND: {field}")
    if target in table.columns:
        raise ValueError(f"OPERATION_FIELD_ALREADY_EXISTS: {target}")
    return table.rename({field: target}), table.height, 0


def _select_fields(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    fields = node.config.get("field_ids")
    if not isinstance(fields, list) or not fields or not all(isinstance(value, str) for value in fields):
        raise ValueError("field_ids must be a non-empty list")
    missing = set(fields) - set(table.columns)
    if missing:
        raise ValueError(f"OPERATION_FIELDS_NOT_FOUND: {sorted(missing)}")
    selected = (["__row_id"] if "__row_id" in table.columns and "__row_id" not in fields else []) + fields
    return table.select(selected), table.height if len(selected) != len(table.columns) else 0, 0


def _reorder_fields(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    fields = node.config.get("field_ids")
    if not isinstance(fields, list) or not all(isinstance(value, str) for value in fields):
        raise ValueError("field_ids must be a list")
    remaining = [column for column in table.columns if column not in fields and column != "__row_id"]
    missing = set(fields) - set(table.columns)
    if missing:
        raise ValueError(f"OPERATION_FIELDS_NOT_FOUND: {sorted(missing)}")
    ordered = (["__row_id"] if "__row_id" in table.columns else []) + fields + remaining
    return table.select(ordered), table.height if ordered != table.columns else 0, 0


def _remove_blank_rows(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    fields = node.config.get("field_ids") or [column for column in table.columns if column != "__row_id"]
    if not isinstance(fields, list) or not all(isinstance(value, str) for value in fields):
        raise ValueError("field_ids must be a list")
    keep = pl.any_horizontal([pl.col(field).is_not_null() & (pl.col(field).cast(pl.String) != "") for field in fields])
    result = table.filter(keep)
    removed = table.height - result.height
    return result, removed, removed


def _remove_repeated_headers(table: pl.DataFrame, node: OperationNode) -> tuple[pl.DataFrame, int, int]:
    values = node.config.get("header_values", {})
    if not isinstance(values, dict) or not values:
        return table, 0, 0
    conditions = [
        pl.col(field).cast(pl.String).str.to_lowercase() == str(value).casefold()
        for field, value in values.items()
        if field in table.columns
    ]
    if not conditions:
        return table, 0, 0
    repeated = pl.all_horizontal(conditions)
    result = table.filter(~repeated)
    removed = table.height - result.height
    return result, removed, removed


Operation = Callable[[pl.DataFrame, OperationNode], tuple[pl.DataFrame, int, int]]
OPERATIONS: dict[str, Operation] = {
    "text.trim": _trim,
    "text.normalise_spaces": _normalise_spaces,
    "text.uppercase": _uppercase,
    "text.lowercase": _lowercase,
    "text.proper_case": _proper_case,
    "text.remove_non_printable": _remove_non_printable,
    "text.normalise_nulls": _normalise_nulls,
    "field.rename": _rename_field,
    "field.select": _select_fields,
    "field.reorder": _reorder_fields,
    "row.remove_blank": _remove_blank_rows,
    "row.remove_repeated_headers": _remove_repeated_headers,
}


def apply_operation(table: pl.DataFrame, node: OperationNode) -> OperationResult:
    if node.operation_version != 1:
        raise ValueError(f"OPERATION_VERSION_UNSUPPORTED: {node.operation_id}@{node.operation_version}")
    operation = OPERATIONS.get(node.operation_id)
    if operation is None:
        raise ValueError(f"OPERATION_NOT_FOUND: {node.operation_id}")
    started = time.perf_counter()
    result, affected, filtered = operation(table, node)
    metric = OperationMetric(
        node_id=node.id,
        operation_id=node.operation_id,
        operation_version=node.operation_version,
        rows_in=table.height,
        rows_out=result.height,
        affected_rows=affected,
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )
    return OperationResult(result, metric, filtered)
