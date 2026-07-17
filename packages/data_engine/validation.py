"""Deterministic validation rule registry."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import polars as pl

from packages.contracts import CanonicalType, ValidationFinding, ValidationRule


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _type_valid(value: Any, expected: CanonicalType) -> bool:
    if _is_missing(value):
        return True
    text = str(value).strip()
    try:
        if expected == CanonicalType.TEXT:
            return True
        if expected == CanonicalType.INTEGER:
            int(text)
            return "." not in text
        if expected == CanonicalType.DECIMAL:
            Decimal(text.replace(",", ""))
            return True
        if expected == CanonicalType.BOOLEAN:
            return text.casefold() in {"true", "false", "yes", "no", "1", "0"}
        if expected == CanonicalType.DATE:
            date.fromisoformat(text)
            return True
        if expected == CanonicalType.DATETIME:
            datetime.fromisoformat(text)
            return True
    except (ValueError, InvalidOperation):
        return False
    return False


def validate_table(table: pl.DataFrame, rules: list[ValidationRule]) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    records = table.to_dicts()
    for rule in rules:
        if rule.field_id not in table.columns:
            raise ValueError(f"VALIDATION_FIELD_NOT_FOUND: {rule.field_id}")
        values = [record.get(rule.field_id) for record in records]
        duplicates = (
            Counter(value for value in values if not _is_missing(value))
            if rule.rule_type == "unique"
            else Counter()
        )
        for index, record in enumerate(records, start=1):
            value = record.get(rule.field_id)
            invalid = False
            if rule.rule_type == "required":
                invalid = _is_missing(value)
            elif rule.rule_type == "data_type":
                expected = CanonicalType(str(rule.config.get("data_type", "text")))
                invalid = not _type_valid(value, expected)
            elif rule.rule_type == "unique":
                invalid = not _is_missing(value) and duplicates[value] > 1
            elif rule.rule_type == "allowed_values":
                allowed = rule.config.get("values", [])
                if not isinstance(allowed, list):
                    raise ValueError("allowed_values config requires values list")
                invalid = not _is_missing(value) and value not in allowed
            elif rule.rule_type == "min_max":
                if not _is_missing(value):
                    try:
                        numeric = Decimal(str(value).replace(",", ""))
                        minimum = rule.config.get("min")
                        maximum = rule.config.get("max")
                        invalid = (minimum is not None and numeric < Decimal(str(minimum))) or (
                            maximum is not None and numeric > Decimal(str(maximum))
                        )
                    except InvalidOperation:
                        invalid = True
            elif rule.rule_type == "text_length":
                if not _is_missing(value):
                    length = len(str(value))
                    minimum = rule.config.get("min")
                    maximum = rule.config.get("max")
                    invalid = (minimum is not None and length < int(minimum)) or (
                        maximum is not None and length > int(maximum)
                    )
            elif rule.rule_type == "regex":
                pattern = rule.config.get("pattern")
                if not isinstance(pattern, str) or len(pattern) > 500:
                    raise ValueError("regex config requires a pattern of at most 500 characters")
                invalid = not _is_missing(value) and re.fullmatch(pattern, str(value)) is None
            if invalid:
                findings.append(
                    ValidationFinding(
                        row_identifier=str(record.get("__row_id", index)),
                        field_identifier=rule.field_id,
                        rule_identifier=rule.id,
                        severity=rule.severity,
                        reason_code=rule.reason_code,
                        explanation=rule.message,
                        original_value=value,
                    )
                )
    return findings
