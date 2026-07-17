"""Measure anonymised Excel export separately from CSV discovery benchmarks."""

from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from uuid import uuid4

import polars as pl

from packages.contracts import SourceHandle, WorkflowConfiguration
from packages.data_engine import Workspace
from packages.data_engine.exporter import export_workbook
from packages.data_engine.resource_policy import iter_csv_batches

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    workflow = WorkflowConfiguration.model_validate_json(
        (ROOT / "samples/workflows/generic_data_quality.json").read_text(encoding="utf-8")
    )
    results = []
    for rows in (10_000, 100_000):
        path = ROOT / ".datapilot/benchmarks" / f"synthetic_{rows}.csv"
        table = pl.concat(list(iter_csv_batches(path, 50_000)))
        with tempfile.TemporaryDirectory(prefix="datapilot-export-benchmark-") as temporary:
            workspace = Workspace(Path(temporary) / "workspace")
            source = workspace.import_source(path, path.name)
            handle = SourceHandle(
                id=source.id,
                project_id=workflow.project_id,
                original_filename=source.original_filename,
                media_type="text/csv",
                size_bytes=source.size_bytes,
                sha256=source.sha256,
            )
            output = Path(temporary) / "output"
            output.mkdir()
            tracemalloc.start()
            started = time.perf_counter()
            workbook = export_workbook(
                output,
                uuid4(),
                source,
                workflow,
                table,
                [],
                [],
                [],
                {"rows_read": rows, "rows_written": rows, "rows_rejected": 0, "rows_filtered": 0},
            )
            duration = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            results.append(
                {
                    "rows": rows,
                    "columns": table.width,
                    "export_seconds": round(duration, 4),
                    "python_peak_bytes": peak,
                    "output_size_bytes": workbook.stat().st_size,
                    "source_id": str(handle.id),
                }
            )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
