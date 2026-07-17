"""Decimal-safe numeric and deterministic date tolerance evaluation."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from packages.contracts import (
    DateTolerance,
    DateToleranceEvidence,
    DateToleranceMode,
    NumericTolerance,
    NumericToleranceEvidence,
    NumericToleranceMode,
)


def as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def compare_numeric(left: Any, right: Any, tolerance: NumericTolerance) -> NumericToleranceEvidence:
    left_decimal = as_decimal(left)
    right_decimal = as_decimal(right)
    if left_decimal is None or right_decimal is None:
        return NumericToleranceEvidence(
            left_value=left_decimal,
            right_value=right_decimal,
            configured_tolerance=tolerance.tolerance,
            mode=tolerance.mode,
            passed=False,
            reason_code="NUMERIC_TOLERANCE_NULL_OR_INVALID",
        )
    if tolerance.mode == NumericToleranceMode.CURRENCY:
        quantum = Decimal(1).scaleb(-tolerance.currency_decimal_places)
        left_decimal = left_decimal.quantize(quantum, rounding=ROUND_HALF_UP)
        right_decimal = right_decimal.quantize(quantum, rounding=ROUND_HALF_UP)
    absolute = abs(left_decimal - right_decimal)
    denominator = max(abs(left_decimal), abs(right_decimal))
    percentage = Decimal(0) if denominator == 0 else absolute / denominator * Decimal(100)
    if tolerance.mode in {NumericToleranceMode.ABSOLUTE, NumericToleranceMode.CURRENCY}:
        passed = absolute <= tolerance.tolerance
    elif tolerance.mode == NumericToleranceMode.PERCENTAGE:
        passed = percentage <= tolerance.tolerance
    else:
        relative = Decimal(0) if denominator == 0 else absolute / denominator
        passed = relative <= tolerance.tolerance
    return NumericToleranceEvidence(
        left_value=left_decimal,
        right_value=right_decimal,
        absolute_difference=absolute,
        percentage_difference=percentage,
        configured_tolerance=tolerance.tolerance,
        mode=tolerance.mode,
        passed=passed,
        reason_code="NUMERIC_TOLERANCE_PASSED" if passed else "NUMERIC_TOLERANCE_EXCEEDED",
    )


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _business_days_between(left: date, right: date, tolerance: DateTolerance) -> int:
    if tolerance.calendar is None:
        raise ValueError("BUSINESS_CALENDAR_REQUIRED")
    start, end = sorted((left, right))
    holidays = set(tolerance.calendar.holidays)
    total = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() not in tolerance.calendar.weekend_days and current not in holidays:
            total += 1
    return total


def compare_dates(left: Any, right: Any, tolerance: DateTolerance) -> DateToleranceEvidence:
    left_date = as_date(left)
    right_date = as_date(right)
    if left_date is None or right_date is None:
        return DateToleranceEvidence(
            left_value=left_date,
            right_value=right_date,
            configured_days=tolerance.days,
            mode=tolerance.mode,
            passed=False,
            reason_code="DATE_TOLERANCE_NULL_OR_INVALID",
        )
    calendar_difference = abs((left_date - right_date).days)
    business_difference: int | None = None
    if tolerance.mode == DateToleranceMode.SAME_DATE:
        passed = calendar_difference == 0
    elif tolerance.mode == DateToleranceMode.CALENDAR_DAYS:
        passed = calendar_difference <= tolerance.days
    elif tolerance.mode == DateToleranceMode.BUSINESS_DAYS:
        business_difference = _business_days_between(left_date, right_date, tolerance)
        passed = business_difference <= tolerance.days
    elif tolerance.mode == DateToleranceMode.MONTH:
        passed = (left_date.year, left_date.month) == (right_date.year, right_date.month)
    else:
        assert tolerance.period_format is not None
        passed = left_date.strftime(tolerance.period_format) == right_date.strftime(tolerance.period_format)
    return DateToleranceEvidence(
        left_value=left_date,
        right_value=right_date,
        calendar_day_difference=calendar_difference,
        business_day_difference=business_difference,
        configured_days=tolerance.days,
        mode=tolerance.mode,
        passed=passed,
        reason_code="DATE_TOLERANCE_PASSED" if passed else "DATE_TOLERANCE_EXCEEDED",
    )
