"""Explicitly regenerate the reviewed anonymised M1B golden workbook."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from packages.contracts import SourceHandle, WorkflowConfiguration
from packages.data_engine import EngineRuntime, Workspace

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    workflow = WorkflowConfiguration.model_validate(
        json.loads((ROOT / "samples/workflows/generic_data_quality.json").read_text(encoding="utf-8"))
    )
    with tempfile.TemporaryDirectory(prefix="datapilot-golden-") as temporary:
        workspace = Workspace(Path(temporary) / "workspace")
        source = workspace.import_source(
            ROOT / "samples/input/anonymised_attendance.csv", "anonymised_attendance.csv"
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
        workbook = next(Path(item) for item in result.record.artifacts if item.endswith(".xlsx"))
        destination = ROOT / "samples/expected_output/generic_data_quality_golden.xlsx"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workbook, destination)
        print(f"Generated reviewed golden workbook: {destination}")


if __name__ == "__main__":
    main()
