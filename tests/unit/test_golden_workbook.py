from __future__ import annotations

from pathlib import Path

import polars as pl
from openpyxl import load_workbook

from packages.contracts import SourceHandle, WorkflowConfiguration
from packages.data_engine import EngineRuntime, Workspace
from packages.data_engine.exporter import export_workbook
from packages.data_engine.golden_workbook import compare_workbook_structure, workbook_signature


def test_current_export_matches_reviewed_golden_structure(
    workflow: WorkflowConfiguration, tmp_path: Path
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    source = workspace.import_source(
        Path("samples/input/anonymised_attendance.csv"), "anonymised_attendance.csv"
    )
    handle = SourceHandle(
        id=source.id,
        project_id=workflow.project_id,
        original_filename=source.original_filename,
        media_type="text/csv",
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    result = EngineRuntime(workspace).execute(source, handle, workflow)
    actual = next(Path(item) for item in result.record.artifacts if item.endswith(".xlsx"))
    golden = Path("samples/expected_output/generic_data_quality_golden.xlsx")
    assert golden.exists()
    assert compare_workbook_structure(golden, actual) == []


def test_structural_comparison_detects_headers_and_formula_injection_is_escaped(
    workflow: WorkflowConfiguration, tmp_path: Path
) -> None:
    workspace = Workspace(tmp_path / "workspace")
    source_path = tmp_path / "formula.csv"
    source_path.write_text("Value\n=2+2\n", encoding="utf-8")
    source = workspace.import_source(source_path, source_path.name)
    output_directory = tmp_path / "outputs"
    output_directory.mkdir()
    output = export_workbook(
        output_directory,
        workflow.id,
        source,
        workflow,
        pl.DataFrame({"value": ["=2+2"]}),
        [],
        [],
        [],
        {"rows_read": 1, "rows_written": 1, "rows_rejected": 0, "rows_filtered": 0},
    )
    signature = workbook_signature(output)
    assert signature["sheets"][0]["formula_cells"] == []
    workbook = load_workbook(output)
    try:
        assert workbook["Processed Data"]["A2"].value == "'=2+2"
        workbook["Processed Data"]["A1"] = "Changed header"
        changed = tmp_path / "changed.xlsx"
        workbook.save(changed)
    finally:
        workbook.close()
    assert any("headers differs" in item for item in compare_workbook_structure(output, changed))
