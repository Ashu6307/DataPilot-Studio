from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
import pytest
from pydantic import ValidationError

from packages.contracts import (
    CalculatedFieldConfiguration,
    CalculationErrorPolicy,
    CanonicalType,
    ExpressionFunction,
    ExpressionNode,
)
from packages.data_engine.expressions import (
    EvaluationContext,
    ExpressionEvaluationError,
    ExpressionTypeError,
    apply_calculation,
    call,
    evaluate_expression,
    field,
    infer_expression_type,
    literal,
)

T = CanonicalType
L = literal


@pytest.mark.parametrize(
    ("function", "args", "expected"),
    [
        (ExpressionFunction.ADD, [L(7, T.INTEGER), L(3, T.INTEGER)], 10),
        (ExpressionFunction.SUBTRACT, [L(7, T.INTEGER), L(3, T.INTEGER)], 4),
        (ExpressionFunction.MULTIPLY, [L(7, T.INTEGER), L(3, T.INTEGER)], 21),
        (ExpressionFunction.DIVIDE, [L(7, T.INTEGER), L(2, T.INTEGER)], Decimal("3.5")),
        (ExpressionFunction.PERCENTAGE, [L(1, T.INTEGER), L(4, T.INTEGER)], Decimal("25.00")),
        (ExpressionFunction.ABSOLUTE, [L(-7, T.INTEGER)], 7),
        (ExpressionFunction.ROUND, [L("3.145", T.DECIMAL), L(2, T.INTEGER)], Decimal("3.15")),
        (ExpressionFunction.MINIMUM, [L(7, T.INTEGER), L(3, T.INTEGER)], 3),
        (ExpressionFunction.MAXIMUM, [L(7, T.INTEGER), L(3, T.INTEGER)], 7),
        (ExpressionFunction.CONCATENATE, [L("A", T.TEXT), L("B", T.TEXT)], "AB"),
        (ExpressionFunction.LENGTH, [L("Data", T.TEXT)], 4),
        (ExpressionFunction.SUBSTRING, [L("DataPilot", T.TEXT), L(4, T.INTEGER), L(5, T.INTEGER)], "Pilot"),
        (ExpressionFunction.STARTS_WITH, [L("DataPilot", T.TEXT), L("Data", T.TEXT)], True),
        (ExpressionFunction.ENDS_WITH, [L("DataPilot", T.TEXT), L("Pilot", T.TEXT)], True),
        (ExpressionFunction.CONTAINS, [L("DataPilot", T.TEXT), L("taPi", T.TEXT)], True),
        (ExpressionFunction.REPLACE, [L("a-b", T.TEXT), L("-", T.TEXT), L("/", T.TEXT)], "a/b"),
        (ExpressionFunction.COALESCE, [L(None, T.TEXT), L("fallback", T.TEXT)], "fallback"),
        (ExpressionFunction.IF, [L(True, T.BOOLEAN), L("yes", T.TEXT), L("no", T.TEXT)], "yes"),
        (ExpressionFunction.AND, [L(True, T.BOOLEAN), L(False, T.BOOLEAN)], False),
        (ExpressionFunction.OR, [L(True, T.BOOLEAN), L(False, T.BOOLEAN)], True),
        (ExpressionFunction.NOT, [L(True, T.BOOLEAN)], False),
        (ExpressionFunction.EQUAL, [L("A", T.TEXT), L("A", T.TEXT)], True),
        (ExpressionFunction.NOT_EQUAL, [L("A", T.TEXT), L("B", T.TEXT)], True),
        (ExpressionFunction.GREATER_THAN, [L(2, T.INTEGER), L(1, T.INTEGER)], True),
        (ExpressionFunction.LESS_THAN, [L(1, T.INTEGER), L(2, T.INTEGER)], True),
        (ExpressionFunction.IS_NULL, [L(None, T.TEXT)], True),
        (ExpressionFunction.IS_NOT_NULL, [L("A", T.TEXT)], True),
        (ExpressionFunction.IN, [L("A", T.TEXT), L("A", T.TEXT), L("B", T.TEXT)], True),
        (ExpressionFunction.DATE_DIFFERENCE, [L("2026-07-17", T.DATE), L("2026-07-01", T.DATE)], 16),
        (ExpressionFunction.ADD_DAYS, [L("2026-07-17", T.DATE), L(2, T.INTEGER)], date(2026, 7, 19)),
        (ExpressionFunction.EXTRACT_YEAR, [L("2026-07-17", T.DATE)], 2026),
        (ExpressionFunction.EXTRACT_MONTH, [L("2026-07-17", T.DATE)], 7),
        (ExpressionFunction.EXTRACT_DAY, [L("2026-07-17", T.DATE)], 17),
        (ExpressionFunction.TODAY, [], date(2026, 7, 17)),
    ],
)
def test_allowlisted_operations(function: ExpressionFunction, args: list[ExpressionNode], expected: object) -> None:
    node = call(function, *args)
    infer_expression_type(node, {})
    assert evaluate_expression(node, EvaluationContext({}, {}, date(2026, 7, 17))) == expected


def test_type_check_rejects_invalid_field_and_operand() -> None:
    with pytest.raises(ExpressionTypeError, match="unknown canonical field"):
        infer_expression_type(field("missing"), {})
    with pytest.raises(ExpressionTypeError, match="incompatible"):
        infer_expression_type(call(ExpressionFunction.ADD, L("x", T.TEXT), L(1, T.INTEGER)), {})


def test_division_by_zero_follows_row_error_policy_and_reports_lineage() -> None:
    config = CalculatedFieldConfiguration(
        calculation_id="ratio",
        output_canonical_field="ratio",
        output_type=T.DECIMAL,
        expression=call(ExpressionFunction.DIVIDE, field("amount"), field("count")),
        error_policy=CalculationErrorPolicy.REJECT_ROW,
        reason_code="CALCULATION_RATIO_FAILED",
        description="Safe ratio",
    )
    table = pl.DataFrame({"__row_id": [1, 2], "amount": ["10", "10"], "count": ["2", "0"]})
    output, result = apply_calculation(
        table,
        config,
        {"amount": T.DECIMAL, "count": T.DECIMAL},
        date(2026, 7, 17),
    )
    assert output.get_column("ratio").to_list()[0] == Decimal("5")
    assert result.failed_rows == 1
    assert result.rejected_row_identifiers == ["2"]
    assert result.lineage_fields == ["amount", "count"]
    assert result.preview[1].error == "division by zero"


def test_expression_contract_prevents_arbitrary_function_or_shape() -> None:
    with pytest.raises(ValidationError):
        ExpressionNode.model_validate({"kind": "call", "function": "__import__", "args": []})
    with pytest.raises(ValidationError):
        ExpressionNode.model_validate({"kind": "field", "field_id": "safe", "args": [{"kind": "literal"}]})
    with pytest.raises(ExpressionEvaluationError, match="division by zero"):
        evaluate_expression(
            call(ExpressionFunction.DIVIDE, L(1, T.INTEGER), L(0, T.INTEGER)),
            EvaluationContext({}, {}, date(2026, 7, 17)),
        )
