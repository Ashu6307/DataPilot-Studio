from __future__ import annotations

import polars as pl
import pytest

from packages.contracts import Severity, ValidationRule
from packages.data_engine.validation import validate_table


@pytest.mark.parametrize(
    ("rule_type", "config", "values"),
    [
        ("required", {}, [""]),
        ("data_type", {"data_type": "integer"}, ["x"]),
        ("unique", {}, ["x", "x"]),
        ("allowed_values", {"values": ["a"]}, ["b"]),
        ("min_max", {"min": 1, "max": 5}, ["9"]),
        ("text_length", {"min": 2, "max": 4}, ["x"]),
        ("regex", {"pattern": "[A-Z]{3}"}, ["ab"]),
    ],
)
def test_validation_rule(rule_type: str, config: dict[str, object], values: list[str]) -> None:
    table = pl.DataFrame({"__row_id": list(range(1, len(values) + 1)), "field": values})
    rule = ValidationRule(
        id="RULE_1",
        rule_type=rule_type,  # type: ignore[arg-type]
        field_id="field",
        severity=Severity.BLOCKING,
        reason_code="FIELD_INVALID",
        message="Field is invalid",
        config=config,
    )
    findings = validate_table(table, [rule])
    assert findings
    assert findings[0].reason_code == "FIELD_INVALID"
    assert findings[0].original_value == values[0]

