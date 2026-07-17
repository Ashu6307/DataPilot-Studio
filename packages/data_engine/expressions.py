"""Closed, typed calculated-field expression engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import polars as pl

from packages.contracts import (
    CalculatedFieldConfiguration,
    CalculationErrorPolicy,
    CalculationPreviewRow,
    CalculationResult,
    CanonicalType,
    ExpressionFunction,
    ExpressionNode,
)

NUMERIC_TYPES = {CanonicalType.INTEGER, CanonicalType.DECIMAL}
DATE_TYPES = {CanonicalType.DATE, CanonicalType.DATETIME}


class ExpressionTypeError(ValueError):
    pass


class ExpressionEvaluationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    row: dict[str, Any]
    field_types: dict[str, CanonicalType]
    execution_date: date


def literal(value: Any, value_type: CanonicalType) -> ExpressionNode:
    return ExpressionNode(kind="literal", value=value, value_type=value_type)


def field(field_id: str) -> ExpressionNode:
    return ExpressionNode(kind="field", field_id=field_id)


def call(function: ExpressionFunction, *args: ExpressionNode) -> ExpressionNode:
    return ExpressionNode(kind="call", function=function, args=list(args))


def _require_arity(function: ExpressionFunction, args: list[CanonicalType], *allowed: int) -> None:
    if len(args) not in allowed:
        expected = " or ".join(str(item) for item in allowed)
        raise ExpressionTypeError(f"{function} expects {expected} argument(s), received {len(args)}")


def _require_types(function: ExpressionFunction, args: list[CanonicalType], allowed: set[CanonicalType]) -> None:
    if any(item not in allowed for item in args):
        raise ExpressionTypeError(f"{function} received incompatible operand types: {args}")


def infer_expression_type(node: ExpressionNode, field_types: dict[str, CanonicalType], depth: int = 0) -> CanonicalType:
    if depth > 32:
        raise ExpressionTypeError("expression nesting exceeds the safe maximum of 32")
    if node.kind == "literal":
        if node.value_type is None:
            raise ExpressionTypeError("literal type is missing")
        return node.value_type
    if node.kind == "field":
        if node.field_id not in field_types:
            raise ExpressionTypeError(f"unknown canonical field reference: {node.field_id}")
        return field_types[node.field_id]
    if node.function is None:
        raise ExpressionTypeError("call function is missing")
    function = node.function
    args = [infer_expression_type(item, field_types, depth + 1) for item in node.args]
    if function in {
        ExpressionFunction.ADD,
        ExpressionFunction.SUBTRACT,
        ExpressionFunction.MULTIPLY,
        ExpressionFunction.DIVIDE,
        ExpressionFunction.PERCENTAGE,
        ExpressionFunction.MINIMUM,
        ExpressionFunction.MAXIMUM,
    }:
        _require_arity(function, args, 2)
        _require_types(function, args, NUMERIC_TYPES)
        return CanonicalType.DECIMAL if CanonicalType.DECIMAL in args or function in {
            ExpressionFunction.DIVIDE,
            ExpressionFunction.PERCENTAGE,
        } else CanonicalType.INTEGER
    if function == ExpressionFunction.ABSOLUTE:
        _require_arity(function, args, 1)
        _require_types(function, args, NUMERIC_TYPES)
        return args[0]
    if function == ExpressionFunction.ROUND:
        _require_arity(function, args, 1, 2)
        _require_types(function, args, NUMERIC_TYPES)
        return CanonicalType.DECIMAL
    if function == ExpressionFunction.CONCATENATE:
        if len(args) < 2:
            raise ExpressionTypeError("concatenate expects at least two arguments")
        return CanonicalType.TEXT
    if function == ExpressionFunction.LENGTH:
        _require_arity(function, args, 1)
        _require_types(function, args, {CanonicalType.TEXT})
        return CanonicalType.INTEGER
    if function == ExpressionFunction.SUBSTRING:
        _require_arity(function, args, 2, 3)
        if args[0] != CanonicalType.TEXT or any(item != CanonicalType.INTEGER for item in args[1:]):
            raise ExpressionTypeError("substring expects text, integer start, and optional integer length")
        return CanonicalType.TEXT
    if function in {
        ExpressionFunction.STARTS_WITH,
        ExpressionFunction.ENDS_WITH,
        ExpressionFunction.CONTAINS,
    }:
        _require_arity(function, args, 2)
        _require_types(function, args, {CanonicalType.TEXT})
        return CanonicalType.BOOLEAN
    if function == ExpressionFunction.REPLACE:
        _require_arity(function, args, 3)
        _require_types(function, args, {CanonicalType.TEXT})
        return CanonicalType.TEXT
    if function == ExpressionFunction.COALESCE:
        if len(args) < 2 or any(item != args[0] for item in args[1:]):
            raise ExpressionTypeError("coalesce expects at least two arguments of the same type")
        return args[0]
    if function == ExpressionFunction.IF:
        _require_arity(function, args, 3)
        if args[0] != CanonicalType.BOOLEAN or args[1] != args[2]:
            raise ExpressionTypeError("if expects boolean condition and matching branch types")
        return args[1]
    if function in {ExpressionFunction.AND, ExpressionFunction.OR}:
        if len(args) < 2:
            raise ExpressionTypeError(f"{function} expects at least two arguments")
        _require_types(function, args, {CanonicalType.BOOLEAN})
        return CanonicalType.BOOLEAN
    if function == ExpressionFunction.NOT:
        _require_arity(function, args, 1)
        _require_types(function, args, {CanonicalType.BOOLEAN})
        return CanonicalType.BOOLEAN
    if function in {ExpressionFunction.EQUAL, ExpressionFunction.NOT_EQUAL}:
        _require_arity(function, args, 2)
        if args[0] != args[1] and not set(args) <= NUMERIC_TYPES:
            raise ExpressionTypeError("equality operands must be type-compatible")
        return CanonicalType.BOOLEAN
    if function in {ExpressionFunction.GREATER_THAN, ExpressionFunction.LESS_THAN}:
        _require_arity(function, args, 2)
        if args[0] != args[1] and not set(args) <= NUMERIC_TYPES:
            raise ExpressionTypeError("comparison operands must be type-compatible")
        return CanonicalType.BOOLEAN
    if function in {ExpressionFunction.IS_NULL, ExpressionFunction.IS_NOT_NULL}:
        _require_arity(function, args, 1)
        return CanonicalType.BOOLEAN
    if function == ExpressionFunction.IN:
        if len(args) < 2 or any(item != args[0] for item in args[1:]):
            raise ExpressionTypeError("in expects a value followed by same-type allowed values")
        return CanonicalType.BOOLEAN
    if function == ExpressionFunction.DATE_DIFFERENCE:
        _require_arity(function, args, 2)
        _require_types(function, args, DATE_TYPES)
        return CanonicalType.INTEGER
    if function == ExpressionFunction.ADD_DAYS:
        _require_arity(function, args, 2)
        if args[0] not in DATE_TYPES or args[1] != CanonicalType.INTEGER:
            raise ExpressionTypeError("add_days expects date/datetime and integer")
        return args[0]
    if function in {
        ExpressionFunction.EXTRACT_YEAR,
        ExpressionFunction.EXTRACT_MONTH,
        ExpressionFunction.EXTRACT_DAY,
    }:
        _require_arity(function, args, 1)
        _require_types(function, args, DATE_TYPES)
        return CanonicalType.INTEGER
    if function == ExpressionFunction.TODAY:
        _require_arity(function, args, 0)
        return CanonicalType.DATE
    raise ExpressionTypeError(f"unsupported expression function: {function}")


def validate_calculation(config: CalculatedFieldConfiguration, field_types: dict[str, CanonicalType]) -> None:
    inferred = infer_expression_type(config.expression, field_types)
    if inferred != config.output_type and not {inferred, config.output_type} <= NUMERIC_TYPES:
        raise ExpressionTypeError(
            f"calculation output type {config.output_type} is incompatible with inferred type {inferred}"
        )


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ExpressionEvaluationError(f"value is not numeric: {value}") from error


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ExpressionEvaluationError(f"value is not an unambiguous ISO date: {value}") from error


def _typed_value(value: Any, value_type: CanonicalType) -> Any:
    if value is None or value == "":
        return None
    if value_type == CanonicalType.INTEGER:
        return int(value)
    if value_type == CanonicalType.DECIMAL:
        return _as_decimal(value)
    if value_type == CanonicalType.BOOLEAN:
        if isinstance(value, bool):
            return value
        lowered = str(value).casefold()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        raise ExpressionEvaluationError(f"value is not boolean: {value}")
    if value_type in DATE_TYPES:
        return _as_date(value)
    return str(value)


def evaluate_expression(node: ExpressionNode, context: EvaluationContext) -> Any:
    if node.kind == "literal":
        if node.value_type is None:
            raise ExpressionEvaluationError("literal type is missing")
        return _typed_value(node.value, node.value_type)
    if node.kind == "field":
        if node.field_id not in context.field_types:
            raise ExpressionEvaluationError(f"unknown canonical field: {node.field_id}")
        return _typed_value(context.row.get(node.field_id), context.field_types[node.field_id])
    if node.function is None:
        raise ExpressionEvaluationError("call function is missing")
    function = node.function
    values = [evaluate_expression(item, context) for item in node.args]
    if function == ExpressionFunction.TODAY:
        return context.execution_date
    if function == ExpressionFunction.IS_NULL:
        return values[0] is None
    if function == ExpressionFunction.IS_NOT_NULL:
        return values[0] is not None
    if function == ExpressionFunction.COALESCE:
        return next((value for value in values if value is not None), None)
    if function == ExpressionFunction.IF:
        return values[1] if values[0] else values[2]
    if any(value is None for value in values):
        return None
    if function == ExpressionFunction.ADD:
        return values[0] + values[1]
    if function == ExpressionFunction.SUBTRACT:
        return values[0] - values[1]
    if function == ExpressionFunction.MULTIPLY:
        return values[0] * values[1]
    if function in {ExpressionFunction.DIVIDE, ExpressionFunction.PERCENTAGE}:
        denominator = _as_decimal(values[1])
        if denominator == 0:
            raise ExpressionEvaluationError("division by zero")
        result = _as_decimal(values[0]) / denominator
        return result * 100 if function == ExpressionFunction.PERCENTAGE else result
    if function == ExpressionFunction.ABSOLUTE:
        return abs(values[0])
    if function == ExpressionFunction.ROUND:
        places = int(values[1]) if len(values) > 1 else 0
        quantum = Decimal(1).scaleb(-places)
        return _as_decimal(values[0]).quantize(quantum, rounding=ROUND_HALF_UP)
    if function == ExpressionFunction.MINIMUM:
        return min(values)
    if function == ExpressionFunction.MAXIMUM:
        return max(values)
    if function == ExpressionFunction.CONCATENATE:
        return "".join(str(value) for value in values)
    if function == ExpressionFunction.LENGTH:
        return len(str(values[0]))
    if function == ExpressionFunction.SUBSTRING:
        start = int(values[1])
        return str(values[0])[start:] if len(values) == 2 else str(values[0])[start : start + int(values[2])]
    if function == ExpressionFunction.STARTS_WITH:
        return str(values[0]).startswith(str(values[1]))
    if function == ExpressionFunction.ENDS_WITH:
        return str(values[0]).endswith(str(values[1]))
    if function == ExpressionFunction.CONTAINS:
        return str(values[1]) in str(values[0])
    if function == ExpressionFunction.REPLACE:
        return str(values[0]).replace(str(values[1]), str(values[2]))
    if function == ExpressionFunction.AND:
        return all(bool(value) for value in values)
    if function == ExpressionFunction.OR:
        return any(bool(value) for value in values)
    if function == ExpressionFunction.NOT:
        return not bool(values[0])
    if function == ExpressionFunction.EQUAL:
        return values[0] == values[1]
    if function == ExpressionFunction.NOT_EQUAL:
        return values[0] != values[1]
    if function == ExpressionFunction.GREATER_THAN:
        return values[0] > values[1]
    if function == ExpressionFunction.LESS_THAN:
        return values[0] < values[1]
    if function == ExpressionFunction.IN:
        return values[0] in values[1:]
    if function == ExpressionFunction.DATE_DIFFERENCE:
        return (_as_date(values[0]) - _as_date(values[1])).days
    if function == ExpressionFunction.ADD_DAYS:
        return _as_date(values[0]) + timedelta(days=int(values[1]))
    if function == ExpressionFunction.EXTRACT_YEAR:
        return _as_date(values[0]).year
    if function == ExpressionFunction.EXTRACT_MONTH:
        return _as_date(values[0]).month
    if function == ExpressionFunction.EXTRACT_DAY:
        return _as_date(values[0]).day
    raise ExpressionEvaluationError(f"unsupported expression function: {function}")


def referenced_fields(node: ExpressionNode) -> list[str]:
    fields = [node.field_id] if node.kind == "field" and node.field_id else []
    for child in node.args:
        fields.extend(referenced_fields(child))
    return list(dict.fromkeys(fields))


def apply_calculation(
    table: pl.DataFrame,
    config: CalculatedFieldConfiguration,
    field_types: dict[str, CanonicalType],
    execution_date: date,
    preview_limit: int = 20,
) -> tuple[pl.DataFrame, CalculationResult]:
    validate_calculation(config, field_types)
    values: list[Any] = []
    failed: list[str] = []
    preview: list[CalculationPreviewRow] = []
    for index, row in enumerate(table.to_dicts(), start=1):
        row_identifier = str(row.get("__row_id", index))
        error_message: str | None = None
        try:
            value = evaluate_expression(
                config.expression,
                EvaluationContext(row=row, field_types=field_types, execution_date=execution_date),
            )
        except (ExpressionEvaluationError, ArithmeticError, ValueError) as error:
            if config.error_policy == CalculationErrorPolicy.STOP:
                raise ExpressionEvaluationError(f"row {row_identifier}: {error}") from error
            value = None
            error_message = str(error)
            failed.append(row_identifier)
        values.append(value)
        if len(preview) < preview_limit:
            preview.append(
                CalculationPreviewRow(
                    row_identifier=row_identifier,
                    before={field_id: row.get(field_id) for field_id in referenced_fields(config.expression)},
                    calculated_value=value,
                    error=error_message,
                )
            )
    output = table.with_columns(pl.Series(config.output_canonical_field, values))
    return output, CalculationResult(
        output_field=config.output_canonical_field,
        calculation_id=config.calculation_id,
        calculation_version=config.version,
        affected_rows=len(values) - len(failed),
        failed_rows=len(failed),
        rejected_row_identifiers=(failed if config.error_policy == CalculationErrorPolicy.REJECT_ROW else []),
        preview=preview,
        lineage_fields=referenced_fields(config.expression),
        reason_code=config.reason_code,
    )
