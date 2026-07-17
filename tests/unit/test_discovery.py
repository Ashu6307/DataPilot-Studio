from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile

import pytest

from packages.contracts import DiscoveryOverrides, SourceHandle
from packages.data_engine.discovery import discover_source
from packages.data_engine.safety import Workspace


def _discover(path: Path, workspace: Workspace, overrides: DiscoveryOverrides):
    source = workspace.import_source(path, path.name)
    handle = SourceHandle(
        id=source.id,
        project_id=uuid4(),
        original_filename=path.name,
        media_type="application/octet-stream",
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    return discover_source(source, handle, overrides)


def test_discovers_csv_header_profile_and_leading_zero(fixture_dir: Path, tmp_path: Path) -> None:
    result = _discover(fixture_dir / "header_row_1.csv", Workspace(tmp_path / "ws"), DiscoveryOverrides())
    table = result.tables[0]
    assert table.selected_header_row == 1
    assert table.column_count == 5
    employee = next(column for column in table.columns if column.source_name == "Employee Code")
    assert employee.is_identifier_candidate
    assert employee.sample_values[0] == "00124"
    assert employee.inferred_type == "text"


def test_discovers_title_rows_and_hidden_sheet(fixture_dir: Path, tmp_path: Path) -> None:
    result = _discover(fixture_dir / "header_after_titles.xlsx", Workspace(tmp_path / "ws"), DiscoveryOverrides())
    visible = next(table for table in result.tables if table.sheet_name == "Attendance import")
    hidden = next(table for table in result.tables if table.sheet_name == "Notes")
    assert visible.selected_header_row == 4
    assert visible.blank_leading_rows == 0  # title rows are populated, not blank
    assert hidden.sheet_state == "hidden"


def test_header_override_is_honoured(fixture_dir: Path, tmp_path: Path) -> None:
    result = _discover(
        fixture_dir / "blank_leading_rows.csv",
        Workspace(tmp_path / "ws"),
        DiscoveryOverrides(header_row=3),
    )
    assert result.tables[0].selected_header_row == 3
    assert result.tables[0].blank_leading_rows == 2


def test_corrupt_workbook_fails_visibly(fixture_dir: Path, tmp_path: Path) -> None:
    with pytest.raises(BadZipFile):
        _discover(fixture_dir / "corrupted.xlsx", Workspace(tmp_path / "ws"), DiscoveryOverrides())
