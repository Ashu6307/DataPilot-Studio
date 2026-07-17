"""Closed-dispatch append, join, aggregation, pivot and unpivot engine."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import polars as pl

from packages.contracts import (
    AggregationConfiguration,
    AggregationFunction,
    AppendConfiguration,
    DuplicateKeyPolicy,
    DuplicateRowPolicy,
    JoinCardinality,
    JoinConfiguration,
    JoinDiagnostics,
    JoinType,
    NullKeyPolicy,
    PivotConfiguration,
    UnpivotConfiguration,
)


@dataclass(slots=True)
class CompositionResult:
    table: pl.DataFrame
    rejected: pl.DataFrame = field(default_factory=pl.DataFrame)
    review: pl.DataFrame = field(default_factory=pl.DataFrame)
    left_unmatched: pl.DataFrame = field(default_factory=pl.DataFrame)
    right_unmatched: pl.DataFrame = field(default_factory=pl.DataFrame)
    duplicate_rows: int = 0
    input_rows: int = 0
    warnings: list[str] = field(default_factory=list)
    join_diagnostics: JoinDiagnostics | None = None


def _duplicate_mask(table: pl.DataFrame, keys: list[str]) -> pl.Series:
    selected = keys or [column for column in table.columns if not column.startswith("__")]
    if not selected:
        return pl.Series("duplicate", [False] * table.height)
    return table.select(pl.struct(selected).is_duplicated().alias("duplicate"))["duplicate"]


def append_tables(tables: list[pl.DataFrame], configuration: AppendConfiguration) -> CompositionResult:
    if not tables:
        return CompositionResult(pl.DataFrame())
    input_rows = sum(table.height for table in tables)
    combined = pl.concat(tables, how="diagonal_relaxed")
    order = [field for field in configuration.output_field_order if field in combined.columns]
    order.extend(column for column in combined.columns if column not in order)
    combined = combined.select(order)
    mask = _duplicate_mask(combined, configuration.duplicate_key_fields)
    duplicate_rows = int(mask.sum())
    rejected = combined.clear()
    review = combined.clear()
    if duplicate_rows and configuration.duplicate_policy in {
        DuplicateRowPolicy.REMOVE_EXACT,
        DuplicateRowPolicy.KEEP_FIRST,
        DuplicateRowPolicy.KEEP_LAST,
    }:
        keep: Literal["first", "last"] = (
            "last" if configuration.duplicate_policy == DuplicateRowPolicy.KEEP_LAST else "first"
        )
        subset = configuration.duplicate_key_fields or [
            column for column in combined.columns if not column.startswith("__")
        ]
        combined = combined.unique(subset=subset, keep=keep, maintain_order=True)
    elif duplicate_rows and configuration.duplicate_policy == DuplicateRowPolicy.REJECT:
        rejected = combined.filter(mask).with_columns(pl.lit("DUPLICATE_ROW_REJECTED").alias("__reason_code"))
        combined = combined.filter(~mask)
    elif duplicate_rows and configuration.duplicate_policy == DuplicateRowPolicy.ROUTE_REVIEW:
        review = combined.filter(mask).with_columns(pl.lit("DUPLICATE_ROW_REVIEW").alias("__reason_code"))
        combined = combined.filter(~mask)
    return CompositionResult(
        table=combined,
        rejected=rejected,
        review=review,
        duplicate_rows=duplicate_rows,
        input_rows=input_rows,
    )


def _normalise_keys(table: pl.DataFrame, keys: list[str], operations: Sequence[str]) -> tuple[pl.DataFrame, list[str]]:
    missing = set(keys) - set(table.columns)
    if missing:
        raise ValueError(f"JOIN_KEYS_NOT_FOUND: {sorted(missing)}")
    generated: list[str] = []
    result = table
    for index, key in enumerate(keys):
        output = f"__join_key_{index}"
        expression = pl.col(key).cast(pl.String, strict=False)
        for operation in operations:
            if operation == "trim":
                expression = expression.str.strip_chars()
            elif operation == "lowercase":
                expression = expression.str.to_lowercase()
            elif operation == "uppercase":
                expression = expression.str.to_uppercase()
            elif operation == "normalise_spaces":
                expression = expression.str.replace_all(r"\s+", " ").str.strip_chars()
        result = result.with_columns(expression.alias(output))
        generated.append(output)
    return result, generated


def _key_counts(table: pl.DataFrame, keys: list[str]) -> Counter[tuple[object, ...]]:
    return Counter(table.select(keys).iter_rows())


def analyse_join_cardinality(
    left: pl.DataFrame,
    right: pl.DataFrame,
    configuration: JoinConfiguration,
) -> JoinDiagnostics:
    left_normalised, keys = _normalise_keys(left, configuration.left_keys, configuration.key_normalisation)
    right_normalised, _ = _normalise_keys(right, configuration.right_keys, configuration.key_normalisation)
    left_counts = _key_counts(left_normalised, keys)
    right_counts = _key_counts(right_normalised, keys)
    null_left = sum(count for key, count in left_counts.items() if any(value is None for value in key))
    null_right = sum(count for key, count in right_counts.items() if any(value is None for value in key))
    comparable_left = {
        key: count
        for key, count in left_counts.items()
        if configuration.null_key_policy == NullKeyPolicy.MATCH_NULLS or all(value is not None for value in key)
    }
    comparable_right = {
        key: count
        for key, count in right_counts.items()
        if configuration.null_key_policy == NullKeyPolicy.MATCH_NULLS or all(value is not None for value in key)
    }
    duplicate_left = sum(count for count in comparable_left.values() if count > 1)
    duplicate_right = sum(count for count in comparable_right.values() if count > 1)
    left_many = any(count > 1 for count in comparable_left.values())
    right_many = any(count > 1 for count in comparable_right.values())
    cardinality = (
        JoinCardinality.MANY_TO_MANY
        if left_many and right_many
        else JoinCardinality.MANY_TO_ONE
        if left_many
        else JoinCardinality.ONE_TO_MANY
        if right_many
        else JoinCardinality.ONE_TO_ONE
    )
    matched_estimate = sum(left_count * comparable_right.get(key, 0) for key, left_count in comparable_left.items())
    left_unmatched = sum(count for key, count in comparable_left.items() if key not in comparable_right) + null_left
    right_unmatched = sum(count for key, count in comparable_right.items() if key not in comparable_left) + null_right
    estimate = matched_estimate
    if configuration.join_type == JoinType.LEFT:
        estimate += left_unmatched
    elif configuration.join_type == JoinType.RIGHT:
        estimate += right_unmatched
    elif configuration.join_type == JoinType.FULL:
        estimate += left_unmatched + right_unmatched
    elif configuration.join_type == JoinType.ANTI:
        estimate = left_unmatched
    elif configuration.join_type == JoinType.SEMI:
        estimate = sum(count for key, count in comparable_left.items() if key in comparable_right)
    blocked = cardinality == JoinCardinality.MANY_TO_MANY and not configuration.approve_many_to_many
    warnings = ["Many-to-many join can expand rows and requires explicit approval"] if blocked else []
    return JoinDiagnostics(
        cardinality=cardinality,
        left_rows=left.height,
        right_rows=right.height,
        estimated_output_rows=estimate,
        expansion_ratio=estimate / max(1, left.height + right.height),
        null_left_keys=null_left,
        null_right_keys=null_right,
        duplicate_left_keys=duplicate_left,
        duplicate_right_keys=duplicate_right,
        blocked=blocked,
        warnings=warnings,
    )


def join_tables(
    left: pl.DataFrame,
    right: pl.DataFrame,
    configuration: JoinConfiguration,
) -> CompositionResult:
    diagnostics = analyse_join_cardinality(left, right, configuration)
    if diagnostics.blocked and configuration.duplicate_key_policy == DuplicateKeyPolicy.BLOCK_MANY_TO_MANY:
        raise ValueError("JOIN_MANY_TO_MANY_APPROVAL_REQUIRED")
    left_work, keys = _normalise_keys(left, configuration.left_keys, configuration.key_normalisation)
    right_work, _ = _normalise_keys(right, configuration.right_keys, configuration.key_normalisation)
    if configuration.null_key_policy == NullKeyPolicy.REJECT and (
        diagnostics.null_left_keys or diagnostics.null_right_keys
    ):
        raise ValueError("JOIN_NULL_KEYS_REJECTED")
    duplicate_groups: list[pl.DataFrame] = []
    for side, table in (("left", left_work), ("right", right_work)):
        duplicate_mask = table.select(pl.struct(keys).is_duplicated().alias("duplicate"))["duplicate"]
        if duplicate_mask.any():
            duplicate_groups.append(
                table.filter(duplicate_mask).with_columns(
                    pl.lit(side).alias("__join_side"),
                    pl.lit("DUPLICATE_JOIN_KEY").alias("__reason_code"),
                )
            )
    if configuration.duplicate_key_policy in {DuplicateKeyPolicy.KEEP_FIRST, DuplicateKeyPolicy.KEEP_LAST}:
        keep: Literal["first", "last"] = (
            "first" if configuration.duplicate_key_policy == DuplicateKeyPolicy.KEEP_FIRST else "last"
        )
        left_work = left_work.unique(subset=keys, keep=keep, maintain_order=True)
        right_work = right_work.unique(subset=keys, keep=keep, maintain_order=True)
    left_unmatched = left_work.join(right_work.select(keys).unique(), on=keys, how="anti")
    right_unmatched = right_work.join(left_work.select(keys).unique(), on=keys, how="anti")
    how_by_type: dict[JoinType, Literal["inner", "left", "right", "full", "semi", "anti"]] = {
        JoinType.INNER: "inner",
        JoinType.LEFT: "left",
        JoinType.RIGHT: "right",
        JoinType.FULL: "full",
        JoinType.SEMI: "semi",
        JoinType.ANTI: "anti",
    }
    joined = left_work.join(
        right_work,
        on=keys,
        how=how_by_type[configuration.join_type],
        suffix=configuration.suffix,
        nulls_equal=configuration.null_key_policy == NullKeyPolicy.MATCH_NULLS,
        coalesce=True,
    )
    joined = joined.drop(keys)
    if configuration.output_fields:
        missing = set(configuration.output_fields) - set(joined.columns)
        if missing:
            raise ValueError(f"JOIN_OUTPUT_FIELDS_NOT_FOUND: {sorted(missing)}")
        joined = joined.select(configuration.output_fields)
    diagnostics = diagnostics.model_copy(
        update={
            "actual_output_rows": joined.height,
            "expansion_ratio": joined.height / max(1, left.height + right.height),
        }
    )
    return CompositionResult(
        table=joined,
        review=pl.concat(duplicate_groups, how="diagonal_relaxed") if duplicate_groups else pl.DataFrame(),
        left_unmatched=left_unmatched,
        right_unmatched=right_unmatched,
        input_rows=left.height + right.height,
        join_diagnostics=diagnostics,
        warnings=diagnostics.warnings,
    )


def _aggregate_expression(measure) -> pl.Expr:  # type: ignore[no-untyped-def]
    expression = pl.col(measure.field_id)
    if measure.null_handling == "zero":
        expression = expression.fill_null(0)
    function = measure.function
    if function == AggregationFunction.SUM:
        return expression.sum().alias(measure.output_field_id)
    if function == AggregationFunction.COUNT:
        return expression.count().alias(measure.output_field_id)
    if function == AggregationFunction.UNIQUE_COUNT:
        return expression.n_unique().alias(measure.output_field_id)
    if function == AggregationFunction.AVERAGE:
        return expression.mean().alias(measure.output_field_id)
    if function == AggregationFunction.MINIMUM:
        return expression.min().alias(measure.output_field_id)
    if function == AggregationFunction.MAXIMUM:
        return expression.max().alias(measure.output_field_id)
    if function == AggregationFunction.MEDIAN:
        return expression.median().alias(measure.output_field_id)
    if function == AggregationFunction.FIRST:
        return expression.first().alias(measure.output_field_id)
    if function == AggregationFunction.LAST:
        return expression.last().alias(measure.output_field_id)
    raise ValueError(f"AGGREGATION_UNSUPPORTED: {function}")


def aggregate_table(table: pl.DataFrame, configuration: AggregationConfiguration) -> CompositionResult:
    required = set(configuration.group_fields) | {measure.field_id for measure in configuration.measures}
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"AGGREGATION_FIELDS_NOT_FOUND: {sorted(missing)}")
    for measure in configuration.measures:
        if measure.null_handling == "error" and table[measure.field_id].null_count():
            raise ValueError(f"AGGREGATION_NULL_VALUES: {measure.field_id}")
        if (
            measure.function
            in {
                AggregationFunction.SUM,
                AggregationFunction.AVERAGE,
                AggregationFunction.MEDIAN,
            }
            and not table.schema[measure.field_id].is_numeric()
        ):
            raise ValueError(f"AGGREGATION_TYPE_INVALID: {measure.field_id}")
    expressions = [_aggregate_expression(measure) for measure in configuration.measures]
    result = table.group_by(configuration.group_fields, maintain_order=True).agg(expressions)
    for field_id in configuration.percentage_of_total_fields:
        if field_id not in result.columns or not result.schema[field_id].is_numeric():
            raise ValueError(f"PERCENTAGE_FIELD_INVALID: {field_id}")
        result = result.with_columns(
            (pl.col(field_id) / pl.col(field_id).sum() * 100).alias(f"{field_id}_percentage_of_total")
        )
    sort_fields = configuration.sort_fields or configuration.group_fields
    result = result.sort(sort_fields, descending=configuration.descending)
    if configuration.rank_field:
        if configuration.rank_field not in result.columns:
            raise ValueError(f"RANK_FIELD_NOT_FOUND: {configuration.rank_field}")
        result = result.with_columns(
            pl.col(configuration.rank_field)
            .rank(method="dense", descending=configuration.descending)
            .alias(configuration.rank_output_field)
        )
    if configuration.running_total_field:
        if configuration.running_total_field not in result.columns:
            raise ValueError(f"RUNNING_TOTAL_FIELD_NOT_FOUND: {configuration.running_total_field}")
        result = result.with_columns(
            pl.col(configuration.running_total_field).cum_sum().alias(configuration.running_total_output_field)
        )
    if configuration.top_n:
        result = result.head(configuration.top_n)
    return CompositionResult(table=result, input_rows=table.height)


def pivot_table(table: pl.DataFrame, configuration: PivotConfiguration) -> CompositionResult:
    required = set(configuration.row_fields + configuration.column_fields + [configuration.value_field])
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"PIVOT_FIELDS_NOT_FOUND: {sorted(missing)}")
    aggregation_map: dict[
        AggregationFunction,
        Literal["sum", "len", "mean", "min", "max", "median", "first", "last"],
    ] = {
        AggregationFunction.SUM: "sum",
        AggregationFunction.COUNT: "len",
        AggregationFunction.AVERAGE: "mean",
        AggregationFunction.MINIMUM: "min",
        AggregationFunction.MAXIMUM: "max",
        AggregationFunction.MEDIAN: "median",
        AggregationFunction.FIRST: "first",
        AggregationFunction.LAST: "last",
    }
    generated = table.select(configuration.column_fields).unique().height
    if generated > configuration.maximum_generated_columns:
        raise ValueError(
            f"PIVOT_GENERATED_COLUMN_LIMIT: estimated {generated}, maximum {configuration.maximum_generated_columns}"
        )
    aggregate_function: Literal["sum", "len", "mean", "min", "max", "median", "first", "last"] | pl.Expr = (
        pl.element().n_unique()
        if configuration.aggregation == AggregationFunction.UNIQUE_COUNT
        else aggregation_map[configuration.aggregation]
    )
    result = table.pivot(
        on=configuration.column_fields,
        index=configuration.row_fields,
        values=configuration.value_field,
        aggregate_function=aggregate_function,
        sort_columns=configuration.sort_columns,
    )
    if configuration.fill_value is not None:
        result = result.fill_null(configuration.fill_value)
    return CompositionResult(
        table=result,
        input_rows=table.height,
        warnings=[f"Pivot generated {max(0, result.width - len(configuration.row_fields))} value column(s)"],
    )


def unpivot_table(table: pl.DataFrame, configuration: UnpivotConfiguration) -> CompositionResult:
    required = set(configuration.identifier_fields + configuration.value_fields)
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"UNPIVOT_FIELDS_NOT_FOUND: {sorted(missing)}")
    result = table.unpivot(
        on=configuration.value_fields,
        index=configuration.identifier_fields,
        variable_name=configuration.variable_field_name,
        value_name=configuration.value_field_name,
    )
    if configuration.null_row_handling == "drop":
        result = result.filter(pl.col(configuration.value_field_name).is_not_null())
    return CompositionResult(table=result, input_rows=table.height)
