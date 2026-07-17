"""Business-key dataset and schema comparison without positional assumptions."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any
from uuid import UUID

import polars as pl

from packages.contracts import (
    CanonicalType,
    ComparisonCategory,
    ComparisonConfiguration,
    ComparisonRecord,
    ComparisonResult,
    ComparisonSummary,
    DifferenceType,
    DriftCategory,
    DriftPolicy,
    FieldComparisonRule,
    FieldDifference,
    KeyNullPolicy,
    Materiality,
    NullEquivalencePolicy,
    RecordReference,
    SchemaExpectation,
    Severity,
    StructureComparisonResult,
    StructureDifference,
    StructureDifferenceCategory,
    TableDiscovery,
)
from packages.data_engine.normalisation import normalise_key, normalise_value
from packages.data_engine.schema_drift import analyze_schema_drift
from packages.data_engine.tolerance import as_decimal, compare_dates, compare_numeric

_LINEAGE_FIELDS = {"__source_id", "__source_file", "__source_table", "__source_row"}


def _reference(dataset_id: UUID, row: dict[str, Any], index: int, key: tuple[Any, ...]) -> RecordReference:
    source_row = row.get("__source_row")
    return RecordReference(
        dataset_id=dataset_id,
        record_id=str(source_row if source_row is not None else index + 1),
        source_row=int(source_row) if isinstance(source_row, int) and source_row > 0 else None,
        business_key=list(key),
    )


def _key(
    row: dict[str, Any],
    fields: list[str],
    configuration: ComparisonConfiguration,
) -> tuple[Any, ...] | None:
    raw = [row.get(field) for field in fields]
    if any(value is None or (isinstance(value, str) and not value.strip()) for value in raw) and (
        configuration.key_null_policy in {KeyNullPolicy.INVALID, KeyNullPolicy.NEVER_MATCH}
    ):
        return None
    pipelines = [configuration.key_normalisation.get(field) for field in fields]
    return normalise_key(raw, pipelines)


def _null_equivalent(left: Any, right: Any, policy: NullEquivalencePolicy) -> bool:
    if policy == NullEquivalencePolicy.STRICT:
        return left is None and right is None
    null_like = {None, "", "null", "none", "n/a", "na"}
    left_normalised = left.strip().casefold() if isinstance(left, str) else left
    right_normalised = right.strip().casefold() if isinstance(right, str) else right
    if policy == NullEquivalencePolicy.EMPTY_EQUALS_NULL:
        return left_normalised in {None, ""} and right_normalised in {None, ""}
    return left_normalised in null_like and right_normalised in null_like


def compare_field(
    business_key: tuple[Any, ...],
    left: Any,
    right: Any,
    rule: FieldComparisonRule,
) -> FieldDifference | None:
    if left is None or right is None or left == "" or right == "":
        if _null_equivalent(left, right, rule.null_equivalence):
            return None
        return FieldDifference(
            business_key=list(business_key),
            field_id=rule.field_id,
            left_value=left,
            right_value=right,
            difference_type=DifferenceType.NULL_CHANGED,
            reason_code="COMPARISON_NULL_CHANGED",
        )
    compared_left, compared_right = left, right
    if rule.normalisation is not None:
        compared_left = normalise_value(left, rule.normalisation).normalised_value
        compared_right = normalise_value(right, rule.normalisation).normalised_value
    if isinstance(compared_left, str) and isinstance(compared_right, str):
        if rule.normalise_whitespace:
            compared_left = " ".join(compared_left.split())
            compared_right = " ".join(compared_right.split())
        if not rule.case_sensitive:
            compared_left = compared_left.casefold()
            compared_right = compared_right.casefold()
    numeric_impact: Decimal | None = None
    difference_type = DifferenceType.VALUE_CHANGED
    if rule.numeric_tolerance is not None:
        numeric_evidence = compare_numeric(compared_left, compared_right, rule.numeric_tolerance)
        if numeric_evidence.passed:
            return None
        numeric_impact = numeric_evidence.absolute_difference
        difference_type = DifferenceType.NUMERIC_CHANGED
    elif rule.date_tolerance is not None:
        date_evidence = compare_dates(compared_left, compared_right, rule.date_tolerance)
        if date_evidence.passed:
            return None
        difference_type = DifferenceType.DATE_CHANGED
    elif compared_left == compared_right:
        return None
    elif type(compared_left) is not type(compared_right):
        difference_type = DifferenceType.TYPE_CHANGED
    elif rule.data_type in {CanonicalType.DECIMAL, CanonicalType.INTEGER}:
        left_decimal, right_decimal = as_decimal(compared_left), as_decimal(compared_right)
        if left_decimal is not None and right_decimal is not None:
            numeric_impact = abs(left_decimal - right_decimal)
            difference_type = DifferenceType.NUMERIC_CHANGED
    materiality = Materiality.NOT_APPLICABLE
    if numeric_impact is not None:
        threshold = rule.materiality_threshold
        materiality = (
            Materiality.MATERIAL if threshold is None or numeric_impact >= threshold else Materiality.IMMATERIAL
        )
    return FieldDifference(
        business_key=list(business_key),
        field_id=rule.field_id,
        left_value=left,
        right_value=right,
        difference_type=difference_type,
        numeric_impact=numeric_impact,
        materiality=materiality,
        reason_code=f"COMPARISON_{difference_type.value.upper()}",
    )


def _index_rows(
    table: pl.DataFrame,
    configuration: ComparisonConfiguration,
    dataset_id: UUID,
) -> tuple[
    dict[tuple[Any, ...], list[tuple[int, dict[str, Any]]]],
    list[tuple[int, dict[str, Any], RecordReference]],
]:
    indexed: dict[tuple[Any, ...], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    invalid: list[tuple[int, dict[str, Any], RecordReference]] = []
    for index, row in enumerate(table.iter_rows(named=True)):
        key = _key(row, configuration.business_key_fields, configuration)
        raw_key = tuple(row.get(field) for field in configuration.business_key_fields)
        if key is None:
            invalid.append((index, row, _reference(dataset_id, row, index, raw_key)))
        else:
            indexed[key].append((index, row))
    return indexed, invalid


def compare_datasets(
    left: pl.DataFrame,
    right: pl.DataFrame,
    configuration: ComparisonConfiguration,
) -> ComparisonResult:
    missing_left = set(configuration.business_key_fields) - set(left.columns)
    missing_right = set(configuration.business_key_fields) - set(right.columns)
    if missing_left or missing_right:
        raise ValueError(f"COMPARISON_KEY_FIELD_MISSING:left={sorted(missing_left)},right={sorted(missing_right)}")
    left_index, invalid_left = _index_rows(left, configuration, configuration.left_dataset_id)
    right_index, invalid_right = _index_rows(right, configuration, configuration.right_dataset_id)
    duplicate_left = {key: rows for key, rows in left_index.items() if len(rows) > 1}
    duplicate_right = {key: rows for key, rows in right_index.items() if len(rows) > 1}
    if configuration.duplicate_key_policy.value == "block" and (duplicate_left or duplicate_right):
        raise ValueError("COMPARISON_DUPLICATE_KEY_BLOCKED")
    records: list[ComparisonRecord] = []
    differences: list[FieldDifference] = []
    for _, _, reference in invalid_left + invalid_right:
        records.append(
            ComparisonRecord(
                category=ComparisonCategory.INVALID_KEY,
                business_key=reference.business_key,
                left=reference if reference.dataset_id == configuration.left_dataset_id else None,
                right=reference if reference.dataset_id == configuration.right_dataset_id else None,
                reason_code="COMPARISON_INVALID_BUSINESS_KEY",
            )
        )
    for side, groups, category, dataset_id in (
        ("left", duplicate_left, ComparisonCategory.DUPLICATE_LEFT, configuration.left_dataset_id),
        ("right", duplicate_right, ComparisonCategory.DUPLICATE_RIGHT, configuration.right_dataset_id),
    ):
        for key, rows in groups.items():
            for index, row in rows:
                reference = _reference(dataset_id, row, index, key)
                records.append(
                    ComparisonRecord(
                        category=category,
                        business_key=list(key),
                        left=reference if side == "left" else None,
                        right=reference if side == "right" else None,
                        reason_code=f"COMPARISON_DUPLICATE_KEY_{side.upper()}",
                    )
                )
    duplicate_keys = set(duplicate_left) | set(duplicate_right)
    if configuration.duplicate_key_policy.value in {"report", "ambiguous"}:
        for key in sorted(duplicate_keys, key=str):
            records.append(
                ComparisonRecord(
                    category=ComparisonCategory.AMBIGUOUS,
                    business_key=list(key),
                    reason_code="COMPARISON_DUPLICATE_KEY_AMBIGUOUS",
                )
            )
    comparable_keys = set(left_index) | set(right_index)
    rules = {rule.field_id: rule for rule in configuration.comparison_rules}
    if configuration.compare_fields:
        fields = configuration.compare_fields
    else:
        fields = sorted((set(left.columns) | set(right.columns)) - set(configuration.ignore_fields) - _LINEAGE_FIELDS)
    fields = [field for field in fields if field not in configuration.business_key_fields]
    for key in sorted(comparable_keys, key=str):
        left_rows = left_index.get(key, [])
        right_rows = right_index.get(key, [])
        if key in duplicate_keys and configuration.duplicate_key_policy.value in {"report", "ambiguous"}:
            continue
        if not left_rows:
            index, row = right_rows[0 if configuration.duplicate_key_policy.value != "keep_last" else -1]
            records.append(
                ComparisonRecord(
                    category=ComparisonCategory.ADDED_RIGHT,
                    business_key=list(key),
                    right=_reference(configuration.right_dataset_id, row, index, key),
                    reason_code="COMPARISON_RECORD_ADDED_RIGHT",
                )
            )
            continue
        if not right_rows:
            index, row = left_rows[0 if configuration.duplicate_key_policy.value != "keep_last" else -1]
            records.append(
                ComparisonRecord(
                    category=ComparisonCategory.REMOVED_RIGHT,
                    business_key=list(key),
                    left=_reference(configuration.left_dataset_id, row, index, key),
                    reason_code="COMPARISON_RECORD_REMOVED_RIGHT",
                )
            )
            continue
        selected = -1 if configuration.duplicate_key_policy.value == "keep_last" else 0
        left_index_value, left_row = left_rows[selected]
        right_index_value, right_row = right_rows[selected]
        row_differences: list[FieldDifference] = []
        for field in fields:
            rule = rules.get(field, FieldComparisonRule(field_id=field))
            difference = compare_field(key, left_row.get(field), right_row.get(field), rule)
            if difference is not None:
                row_differences.append(difference)
        category = ComparisonCategory.MODIFIED if row_differences else ComparisonCategory.UNCHANGED
        records.append(
            ComparisonRecord(
                category=category,
                business_key=list(key),
                left=_reference(configuration.left_dataset_id, left_row, left_index_value, key),
                right=_reference(configuration.right_dataset_id, right_row, right_index_value, key),
                differences=row_differences,
                reason_code="COMPARISON_RECORD_MODIFIED" if row_differences else "COMPARISON_RECORD_UNCHANGED",
            )
        )
        differences.extend(row_differences)
    counts = Counter(record.category for record in records)
    summary = ComparisonSummary(
        total_left_rows=left.height,
        total_right_rows=right.height,
        matched_keys=counts[ComparisonCategory.MODIFIED] + counts[ComparisonCategory.UNCHANGED],
        added=counts[ComparisonCategory.ADDED_RIGHT],
        removed=counts[ComparisonCategory.REMOVED_RIGHT],
        modified=counts[ComparisonCategory.MODIFIED],
        unchanged=counts[ComparisonCategory.UNCHANGED],
        duplicate_left_keys=len(duplicate_left),
        duplicate_right_keys=len(duplicate_right),
        invalid_left_keys=len(invalid_left),
        invalid_right_keys=len(invalid_right),
        ambiguous=counts[ComparisonCategory.AMBIGUOUS],
    )
    return ComparisonResult(
        configuration_id=configuration.id,
        configuration_version=configuration.version,
        records=records,
        field_differences=differences,
        summary=summary,
    )


_DRIFT_MAP = {
    DriftCategory.COLUMN_ADDED: StructureDifferenceCategory.ADDED_COLUMN,
    DriftCategory.OPTIONAL_COLUMN_REMOVED: StructureDifferenceCategory.REMOVED_COLUMN,
    DriftCategory.REQUIRED_COLUMN_REMOVED: StructureDifferenceCategory.REMOVED_COLUMN,
    DriftCategory.COLUMN_RENAMED: StructureDifferenceCategory.RENAMED_OR_REMAPPED,
    DriftCategory.AMBIGUOUS_MAPPING: StructureDifferenceCategory.RENAMED_OR_REMAPPED,
    DriftCategory.COLUMN_REORDERED: StructureDifferenceCategory.REORDERED_COLUMN,
    DriftCategory.DATA_TYPE_CHANGED: StructureDifferenceCategory.DATA_TYPE_CHANGED,
    DriftCategory.NULLABILITY_CHANGED: StructureDifferenceCategory.NULLABILITY_CHANGED,
    DriftCategory.NEW_UNEXPECTED_VALUES: StructureDifferenceCategory.UNEXPECTED_VALUES,
    DriftCategory.DUPLICATE_COLUMN_INTRODUCED: StructureDifferenceCategory.KEY_UNIQUENESS_CHANGED,
    DriftCategory.HEADER_LEVEL_CHANGED: StructureDifferenceCategory.HEADER_LEVEL_CHANGED,
    DriftCategory.SHEET_RENAMED: StructureDifferenceCategory.SELECTED_TABLE_CHANGED,
    DriftCategory.SELECTED_TABLE_MOVED: StructureDifferenceCategory.SELECTED_TABLE_CHANGED,
}


def compare_structures(
    expectation: SchemaExpectation,
    observed: TableDiscovery,
    policy: DriftPolicy | None = None,
    *,
    expected_key_unique: bool | None = None,
    observed_key_unique: bool | None = None,
) -> StructureComparisonResult:
    drift = analyze_schema_drift(expectation, observed, policy or DriftPolicy())
    output: list[StructureDifference] = []
    for finding in drift.findings:
        impact = "breaking" if finding.blocking else "review"
        if finding.category in {DriftCategory.COLUMN_REORDERED, DriftCategory.COLUMN_ADDED}:
            impact = "compatible"
        output.append(
            StructureDifference(
                category=_DRIFT_MAP[finding.category],
                field_id=finding.canonical_field_id,
                left_value=finding.expected,
                right_value=finding.observed,
                severity=Severity.ERROR if finding.blocking else Severity.WARNING,
                compatibility_impact=impact,
                recommended_action="Review and version the canonical mapping before workflow reuse",
                workflow_reuse_impact="blocked" if finding.blocking else "requires compatibility review",
                reason_code=f"STRUCTURE_{_DRIFT_MAP[finding.category].value.upper()}",
            )
        )
    if (
        expected_key_unique is not None
        and observed_key_unique is not None
        and expected_key_unique != observed_key_unique
    ):
        output.append(
            StructureDifference(
                category=StructureDifferenceCategory.KEY_UNIQUENESS_CHANGED,
                left_value=expected_key_unique,
                right_value=observed_key_unique,
                severity=Severity.ERROR,
                compatibility_impact="breaking",
                recommended_action="Review key definition and duplicate policy",
                workflow_reuse_impact="matching cardinality must be revalidated",
                reason_code="STRUCTURE_KEY_UNIQUENESS_CHANGED",
            )
        )
    summary = Counter(item.category.value for item in output)
    return StructureComparisonResult(
        differences=output,
        compatible=not any(item.compatibility_impact == "breaking" for item in output),
        requires_review=bool(output),
        summary=dict(summary),
    )
