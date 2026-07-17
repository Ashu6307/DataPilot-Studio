"""Run reproducible local M1B performance measurements without customer data."""

from __future__ import annotations

import csv
import json
import platform
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from packages.contracts import DiscoveryOverrides, OperationNode, SourceHandle
from packages.data_engine import Workspace, discover_source, read_selected_table
from packages.data_engine.operations import apply_operation
from packages.data_engine.resource_policy import iter_csv_batches

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = ROOT / ".datapilot" / "benchmarks"


def _measure[T](action: Callable[[], T]) -> tuple[T, float, int]:
    tracemalloc.start()
    started = time.perf_counter()
    result = action()
    duration = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, duration, peak


def _fixture(path: Path, rows: int, columns: int = 8) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = ["Record ID", "Name", "Status", "Amount", "Work Date"] + [
        f"Metric {index}" for index in range(max(0, columns - 5))
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        for index in range(rows):
            writer.writerow(
                [
                    f"{index:09d}",
                    f"Synthetic Person {index}",
                    "active" if index % 2 == 0 else "inactive",
                    f"{index % 10000}.{index % 100:02d}",
                    "2026-07-17",
                    *[str((index + column) % 1000) for column in range(max(0, columns - 5))],
                ]
            )


def _measure_dataset(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "file": path.name,
        "size_bytes": path.stat().st_size,
    }
    (read_rows, read_seconds, read_peak) = _measure(
        lambda: sum(batch.height for batch in iter_csv_batches(path, 50_000))
    )
    result.update(
        {
            "rows": read_rows,
            "batched_read_seconds": round(read_seconds, 4),
            "batched_read_python_peak_bytes": read_peak,
        }
    )

    def process() -> int:
        processed = 0
        node = OperationNode(operation_id="text.trim", config={"field_id": "Name"})
        for batch in iter_csv_batches(path, 50_000):
            processed += apply_operation(batch, node).table.height
        return processed

    (_, processing_seconds, processing_peak) = _measure(process)
    result.update(
        {
            "batched_processing_seconds": round(processing_seconds, 4),
            "batched_processing_python_peak_bytes": processing_peak,
        }
    )
    with tempfile.TemporaryDirectory(prefix="datapilot-benchmark-") as temporary:
        workspace = Workspace(Path(temporary) / "workspace")
        source = workspace.import_source(path, path.name)
        handle = SourceHandle(
            id=source.id,
            project_id=uuid4(),
            original_filename=source.original_filename,
            media_type="text/csv",
            size_bytes=source.size_bytes,
            sha256=source.sha256,
        )
        (discovery, discovery_seconds, discovery_peak) = _measure(
            lambda: discover_source(source, handle, DiscoveryOverrides())
        )
        (_, preview_seconds, preview_peak) = _measure(
            lambda: read_selected_table(source, DiscoveryOverrides(), 200)
        )
        result.update(
            {
                "columns": discovery.tables[0].column_count,
                "discovery_seconds": round(discovery_seconds, 4),
                "discovery_python_peak_bytes": discovery_peak,
                "preview_200_seconds": round(preview_seconds, 4),
                "preview_200_python_peak_bytes": preview_peak,
            }
        )
    return result


def main() -> None:
    datasets = []
    for rows in (10_000, 100_000, 500_000):
        path = BENCHMARK_ROOT / f"synthetic_{rows}.csv"
        _fixture(path, rows)
        datasets.append(_measure_dataset(path))
    wide = BENCHMARK_ROOT / "synthetic_wide_1000x250.csv"
    _fixture(wide, 1_000, 250)
    datasets.append(_measure_dataset(wide))
    print(
        json.dumps(
            {
                "measured_at": "2026-07-17",
                "platform": platform.platform(),
                "python": platform.python_version(),
                "datasets": datasets,
                "limitations": [
                    "tracemalloc reports Python allocations and excludes some Polars/native allocations",
                    "export timing is covered by the golden/runtime performance tests, not this CSV-stage script",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
