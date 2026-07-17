from __future__ import annotations

import zipfile
from pathlib import Path
from uuid import uuid4

import polars as pl

from packages.contracts import CanonicalType, ExpressionFunction, ExpressionNode, SplitConfiguration, SplitMode
from packages.data_engine.batch_exporter import (
    export_split_outputs,
    naming_preview,
    safe_output_name,
    safe_sheet_name,
    split_table,
)


def test_split_names_prevent_traversal_invalid_characters_and_sheet_overflow() -> None:
    assert safe_output_name("../../Finance:North*?") == "Finance_North"
    assert safe_output_name("CON") == "_CON"
    assert safe_sheet_name("'Finance'") == "Finance"
    assert len(safe_sheet_name("a" * 80)) == 31
    preview = naming_preview(
        SplitConfiguration(fields=["department"], naming_template="{project}_{split_value}_{run_date}"),
        "../Finance:North",
        "2026-07-17",
    )
    assert "/" not in preview and ".." not in preview and ":" not in preview


def test_split_by_multiple_fields_and_row_limit_reconciles() -> None:
    table = pl.DataFrame(
        {"department": ["A", "A", "A", "B"], "month": ["Jan", "Jan", "Jan", "Feb"], "value": [1, 2, 3, 4]}
    )
    groups = split_table(
        table,
        SplitConfiguration(fields=["department", "month"], maximum_rows_per_file=2),
    )
    assert sorted(groups) == ["A__Jan_part_1", "A__Jan_part_2", "B__Feb"]
    assert sum(group.height for group in groups.values()) == table.height


def test_split_condition_uses_closed_typed_expression_engine() -> None:
    table = pl.DataFrame({"department": ["A", "B", "A"], "value": [1, 2, 3]})
    condition = ExpressionNode(
        kind="call",
        function=ExpressionFunction.GREATER_THAN,
        args=[
            ExpressionNode(kind="field", field_id="value"),
            ExpressionNode(kind="literal", value=1, value_type=CanonicalType.INTEGER),
        ],
    )
    groups = split_table(table, SplitConfiguration(fields=["department"], condition=condition))
    assert sorted(groups) == ["A", "B"]
    assert sum(group.height for group in groups.values()) == 2


def test_deterministic_zip_contains_only_derived_outputs(tmp_path: Path) -> None:
    table = pl.DataFrame({"department": ["A", "B"], "value": [1, 2]})
    entries = export_split_outputs(
        tmp_path,
        uuid4(),
        table,
        SplitConfiguration(fields=["department"], mode=SplitMode.ZIP_PACKAGE),
    )
    archive = next(tmp_path / entry.relative_path for entry in entries if entry.media_type == "application/zip")
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
    assert names == ["datapilot_A_2026-07-17.csv", "datapilot_B_2026-07-17.csv", "output-manifest.json"]
    assert all("input" not in name.casefold() for name in names)


def test_duplicate_sanitised_split_names_receive_collision_suffix(tmp_path: Path) -> None:
    table = pl.DataFrame({"department": ["Finance/North", "Finance\\North"], "value": [1, 2]})
    entries = export_split_outputs(
        tmp_path,
        uuid4(),
        table,
        SplitConfiguration(fields=["department"], mode=SplitMode.CSV_FILES),
    )
    assert sorted(entry.relative_path for entry in entries) == [
        "datapilot_Finance_North_2026-07-17.csv",
        "datapilot_Finance_North_2026-07-17_2.csv",
    ]
