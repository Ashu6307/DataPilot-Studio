from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from packages.contracts import DiscoveryOverrides, SourceHandle
from packages.data_engine.discovery import discover_source, read_selected_table
from packages.data_engine.safety import Workspace


def _discover(path: Path, tmp_path: Path, overrides: DiscoveryOverrides | None = None):
    workspace = Workspace(tmp_path / "workspace")
    source = workspace.import_source(path, path.name)
    handle = SourceHandle(
        id=source.id,
        project_id=uuid4(),
        original_filename=path.name,
        media_type="application/octet-stream",
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    return source, discover_source(source, handle, overrides or DiscoveryOverrides())


def test_two_and_three_level_headers_flatten(fixture_dir: Path, tmp_path: Path) -> None:
    _, two = _discover(fixture_dir / "two_row_header.xlsx", tmp_path / "two")
    assert two.tables[0].selected_header_rows == [1, 2]
    assert [column.source_name for column in two.tables[0].columns] == [
        "Identity.Code",
        "Identity.Name",
        "Performance.Target",
        "Performance.Actual",
    ]

    _, three = _discover(fixture_dir / "three_row_header.xlsx", tmp_path / "three")
    assert three.tables[0].selected_header_rows == [1, 2, 3]
    assert three.tables[0].columns[2].source_name == "Measures.Current.Target"


def test_merged_headers_are_forward_filled_and_separator_is_configurable(
    fixture_dir: Path, tmp_path: Path
) -> None:
    _, result = _discover(
        fixture_dir / "merged_header.xlsx",
        tmp_path,
        DiscoveryOverrides(header_flattening_separator="/"),
    )
    table = result.tables[0]
    assert table.selected_header_rows == [1, 2]
    assert [column.source_name for column in table.columns] == [
        "Identity/Code",
        "Identity/Name",
        "Performance/Target",
        "Performance/Actual",
    ]
    assert any("merged header" in item for item in table.evidence)


def test_multiple_tables_are_separate_selectable_candidates(fixture_dir: Path, tmp_path: Path) -> None:
    _, row_result = _discover(fixture_dir / "multiple_tables_rows.xlsx", tmp_path / "rows")
    assert len(row_result.tables) == 2
    assert [(table.start_row, table.end_row) for table in row_result.tables] == [(1, 2), (4, 5)]

    source, column_result = _discover(fixture_dir / "multiple_tables_columns.xlsx", tmp_path / "columns")
    assert len(column_result.tables) == 2
    selected = column_result.tables[1]
    frame = read_selected_table(
        source,
        DiscoveryOverrides(sheet_name="Column regions", table_id=selected.table_id),
    )
    assert frame.columns == ["Item", "Quantity"]
    assert frame.height == 2
    assert selected.table_id in column_result.tables[0].alternative_candidates


def test_repeated_headers_and_footers_are_classified_not_deleted(fixture_dir: Path, tmp_path: Path) -> None:
    _, repeated = _discover(fixture_dir / "repeated_header_rows.csv", tmp_path / "repeated")
    assert repeated.tables[0].repeated_header_rows == [4]
    assert repeated.tables[0].row_count_estimate == 4

    _, result = _discover(fixture_dir / "footer_subtotals.xlsx", tmp_path / "footer")
    kinds = {item.classification for item in result.tables[0].row_classifications}
    assert {"subtotal", "grand_total", "generated_footer", "note", "signature"} <= kinds
    assert result.tables[0].footer_rows == [3, 5, 6, 7, 8]


def test_header_override_and_duplicate_disambiguation_are_explicit(fixture_dir: Path, tmp_path: Path) -> None:
    _, result = _discover(
        fixture_dir / "ambiguous_header_candidates.csv",
        tmp_path,
        DiscoveryOverrides(header_rows=[2]),
    )
    table = result.tables[0]
    assert table.selected_header_rows == [2]
    assert table.user_override["header_rows"] == [2]
    assert table.decision.endswith("header rows [2]")
