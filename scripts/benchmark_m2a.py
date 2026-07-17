"""Reproducible local benchmarks for Milestone 2A composition operations."""

from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl

from packages.contracts import (
    AppendConfiguration,
    JoinConfiguration,
    JoinType,
    PivotConfiguration,
    SplitConfiguration,
    SplitMode,
)
from packages.data_engine.batch_exporter import export_split_outputs
from packages.data_engine.composition import append_tables, join_tables, pivot_table

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "composition"


def measured(name: str, action: Callable[[], Any]) -> dict[str, Any]:
    tracemalloc.start()
    started = time.perf_counter()
    result = action()
    duration = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rows = result.table.height if hasattr(result, "table") else int(result)
    return {"scenario": name, "seconds": round(duration, 4), "python_peak_bytes": peak, "output_rows": rows}


def main() -> None:
    append_inputs = [pl.read_csv(path) for path in sorted(FIXTURES.glob("large_append_*.csv"))]
    left = pl.DataFrame({"id": range(100_000), "left_value": range(100_000)})
    right = pl.DataFrame({"id": range(20_000, 120_000), "right_value": range(100_000)})
    pivot_input = pl.DataFrame(
        {
            "entity": [f"E{(index // 100) % 1_000:04d}" for index in range(100_000)],
            "period": [f"P{index % 100:03d}" for index in range(100_000)],
            "value": [index % 500 for index in range(100_000)],
        }
    )
    split_input = pl.DataFrame(
        {"department": [f"D{index % 20:02d}" for index in range(100_000)], "value": range(100_000)}
    )
    results = [
        measured("append_10_files_100k_rows", lambda: append_tables(append_inputs, AppendConfiguration())),
        measured(
            "left_join_100k_by_100k",
            lambda: join_tables(
                left,
                right,
                JoinConfiguration(
                    left_source_id=uuid4(),
                    right_source_id=uuid4(),
                    join_type=JoinType.LEFT,
                    left_keys=["id"],
                    right_keys=["id"],
                ),
            ),
        ),
        measured(
            "pivot_100k_to_100_columns",
            lambda: pivot_table(
                pivot_input,
                PivotConfiguration(row_fields=["entity"], column_fields=["period"], value_field="value"),
            ),
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="datapilot-m2a-") as directory:
        results.append(
            measured(
                "split_100k_to_20_csv_files",
                lambda: sum(
                    entry.rows
                    for entry in export_split_outputs(
                        Path(directory),
                        uuid4(),
                        split_input,
                        SplitConfiguration(fields=["department"], mode=SplitMode.CSV_FILES),
                    )
                ),
            )
        )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
