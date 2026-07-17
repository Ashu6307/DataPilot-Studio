from __future__ import annotations

from uuid import uuid4

import polars as pl
import pytest

from packages.contracts import OperationNode
from packages.data_engine.operations import apply_operation


@pytest.mark.parametrize(
    ("operation_id", "value", "expected"),
    [
        ("text.trim", "  A  ", "A"),
        ("text.normalise_spaces", "A   B", "A B"),
        ("text.uppercase", "Ab", "AB"),
        ("text.lowercase", "Ab", "ab"),
        ("text.proper_case", "aNITA rAO", "Anita Rao"),
        ("text.remove_non_printable", "A\x00B", "AB"),
    ],
)
def test_text_operation(operation_id: str, value: str, expected: str) -> None:
    result = apply_operation(
        pl.DataFrame({"__row_id": [1], "name": [value]}),
        OperationNode(id=uuid4(), operation_id=operation_id, config={"field_id": "name"}),
    )
    assert result.table.item(0, "name") == expected
    assert result.metric.affected_rows == 1


def test_null_normalisation() -> None:
    result = apply_operation(
        pl.DataFrame({"__row_id": [1, 2], "value": ["N/A", "ok"]}),
        OperationNode(operation_id="text.normalise_nulls", config={"field_id": "value"}),
    )
    assert result.table.get_column("value").to_list() == [None, "ok"]


def test_field_rename_select_and_reorder() -> None:
    table = pl.DataFrame({"__row_id": [1], "a": ["x"], "b": ["y"], "c": ["z"]})
    renamed = apply_operation(
        table,
        OperationNode(
            operation_id="field.rename",
            config={"field_id": "a", "new_field_id": "alpha"},
        ),
    ).table
    reordered = apply_operation(
        renamed,
        OperationNode(operation_id="field.reorder", config={"field_ids": ["c", "alpha"]}),
    ).table
    selected = apply_operation(
        reordered,
        OperationNode(operation_id="field.select", config={"field_ids": ["alpha", "c"]}),
    ).table
    assert selected.columns == ["__row_id", "alpha", "c"]


def test_blank_and_repeated_header_rows_are_filtered() -> None:
    table = pl.DataFrame({"__row_id": [1, 2, 3], "name": ["", "Name", "A"], "code": ["", "Code", "1"]})
    no_blank = apply_operation(table, OperationNode(operation_id="row.remove_blank", config={})).table
    result = apply_operation(
        no_blank,
        OperationNode(
            operation_id="row.remove_repeated_headers",
            config={"header_values": {"name": "Name", "code": "Code"}},
        ),
    )
    assert result.table.height == 1
    assert result.filtered_rows == 1


def test_unknown_operation_fails() -> None:
    with pytest.raises(ValueError, match="OPERATION_NOT_FOUND"):
        apply_operation(pl.DataFrame({"a": ["x"]}), OperationNode(operation_id="unknown.operation"))
