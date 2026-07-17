from __future__ import annotations

from uuid import uuid4

import polars as pl
import pytest

from packages.contracts import (
    AggregationConfiguration,
    AggregationFunction,
    AggregationMeasure,
    AppendConfiguration,
    DuplicateRowPolicy,
    JoinCardinality,
    JoinConfiguration,
    JoinType,
    NullKeyPolicy,
    PivotConfiguration,
    UnpivotConfiguration,
)
from packages.data_engine.composition import (
    aggregate_table,
    analyse_join_cardinality,
    append_tables,
    join_tables,
    pivot_table,
    unpivot_table,
)


def test_append_reorders_by_name_preserves_lineage_and_routes_duplicates() -> None:
    first = pl.DataFrame({"id": ["001", "002"], "amount": [10.0, 20.0], "__source_file": ["a.csv", "a.csv"]})
    second = pl.DataFrame({"amount": [10.0, 30.0], "id": ["001", "003"], "__source_file": ["b.csv", "b.csv"]})
    result = append_tables(
        [first, second],
        AppendConfiguration(
            output_field_order=["id", "amount"],
            duplicate_policy=DuplicateRowPolicy.ROUTE_REVIEW,
            duplicate_key_fields=["id", "amount"],
        ),
    )
    assert result.input_rows == 4
    assert result.duplicate_rows == 2
    assert result.table.height == 2
    assert result.review.height == 2
    assert result.table.columns[:2] == ["id", "amount"]


def _join_config(join_type: JoinType, approve: bool = False) -> JoinConfiguration:
    return JoinConfiguration(
        left_source_id=uuid4(),
        right_source_id=uuid4(),
        join_type=join_type,
        left_keys=["key"],
        right_keys=["key"],
        key_normalisation=["trim", "lowercase"],
        approve_many_to_many=approve,
    )


def test_join_cardinality_blocks_unapproved_many_to_many_and_reports_expansion() -> None:
    left = pl.DataFrame({"key": [" A ", "a", "b"], "left_value": [1, 2, 3]})
    right = pl.DataFrame({"key": ["a", "A", "c"], "right_value": [10, 20, 30]})
    config = _join_config(JoinType.INNER)
    diagnostics = analyse_join_cardinality(left, right, config)
    assert diagnostics.cardinality == JoinCardinality.MANY_TO_MANY
    assert diagnostics.estimated_output_rows == 4
    assert diagnostics.blocked
    with pytest.raises(ValueError, match="JOIN_MANY_TO_MANY_APPROVAL_REQUIRED"):
        join_tables(left, right, config)
    approved = join_tables(left, right, config.model_copy(update={"approve_many_to_many": True}))
    assert approved.table.height == 4
    assert approved.join_diagnostics is not None
    assert approved.join_diagnostics.actual_output_rows == 4
    assert approved.review.height == 4
    assert set(approved.review["__reason_code"]) == {"DUPLICATE_JOIN_KEY"}


@pytest.mark.parametrize(
    ("join_type", "expected"),
    [
        (JoinType.INNER, 1),
        (JoinType.LEFT, 2),
        (JoinType.RIGHT, 2),
        (JoinType.FULL, 3),
        (JoinType.SEMI, 1),
        (JoinType.ANTI, 1),
    ],
)
def test_all_exact_join_types(join_type: JoinType, expected: int) -> None:
    left = pl.DataFrame({"key": ["a", "b"], "left_value": [1, 2]})
    right = pl.DataFrame({"key": ["a", "c"], "right_value": [10, 30]})
    result = join_tables(left, right, _join_config(join_type))
    assert result.table.height == expected


def test_join_null_key_policies_are_explicit() -> None:
    left = pl.DataFrame({"key": [None, "a"], "left_value": [1, 2]})
    right = pl.DataFrame({"key": [None, "a"], "right_value": [10, 20]})
    never = join_tables(left, right, _join_config(JoinType.INNER))
    assert never.table.height == 1
    matched = join_tables(
        left,
        right,
        _join_config(JoinType.INNER).model_copy(update={"null_key_policy": NullKeyPolicy.MATCH_NULLS}),
    )
    assert matched.table.height == 2
    with pytest.raises(ValueError, match="JOIN_NULL_KEYS_REJECTED"):
        join_tables(
            left,
            right,
            _join_config(JoinType.INNER).model_copy(update={"null_key_policy": NullKeyPolicy.REJECT}),
        )


def test_grouped_aggregation_rank_percentage_and_running_total() -> None:
    table = pl.DataFrame({"region": ["North", "North", "South"], "amount": [10.0, 20.0, 5.0], "item": ["a", "b", "a"]})
    functions = [
        AggregationFunction.SUM,
        AggregationFunction.COUNT,
        AggregationFunction.UNIQUE_COUNT,
        AggregationFunction.AVERAGE,
        AggregationFunction.MINIMUM,
        AggregationFunction.MAXIMUM,
        AggregationFunction.MEDIAN,
        AggregationFunction.FIRST,
        AggregationFunction.LAST,
    ]
    measures = [
        AggregationMeasure(
            field_id="item" if function == AggregationFunction.UNIQUE_COUNT else "amount",
            function=function,
            output_field_id=f"metric_{function.value}",
        )
        for function in functions
    ]
    result = aggregate_table(
        table,
        AggregationConfiguration(
            group_fields=["region"],
            measures=measures,
            sort_fields=["metric_sum"],
            descending=True,
            percentage_of_total_fields=["metric_sum"],
            rank_field="metric_sum",
            running_total_field="metric_sum",
        ),
    ).table
    assert result.height == 2
    assert result["metric_sum"].to_list() == [30.0, 5.0]
    assert round(sum(result["metric_sum_percentage_of_total"]), 6) == 100
    assert result["rank"].to_list() == [1, 2]
    assert result["running_total"].to_list() == [30.0, 35.0]


def test_pivot_and_unpivot_report_shape() -> None:
    table = pl.DataFrame({"region": ["North", "North", "South"], "month": ["Jan", "Feb", "Jan"], "amount": [10, 20, 5]})
    pivoted = pivot_table(
        table,
        PivotConfiguration(row_fields=["region"], column_fields=["month"], value_field="amount"),
    ).table
    assert pivoted.height == 2
    assert {"Jan", "Feb"} <= set(pivoted.columns)
    unpivoted = unpivot_table(
        pivoted,
        UnpivotConfiguration(identifier_fields=["region"], value_fields=["Jan", "Feb"]),
    ).table
    assert unpivoted.height == 4
    assert {"variable", "value"} <= set(unpivoted.columns)


def test_wide_pivot_blocks_before_generation() -> None:
    table = pl.DataFrame({"row": ["a", "a", "a"], "column": ["x", "y", "z"], "value": [1, 2, 3]})
    with pytest.raises(ValueError, match="PIVOT_GENERATED_COLUMN_LIMIT"):
        pivot_table(
            table,
            PivotConfiguration(
                row_fields=["row"], column_fields=["column"], value_field="value", maximum_generated_columns=2
            ),
        )
