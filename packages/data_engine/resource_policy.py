"""Configurable resource-risk estimation and genuine batched CSV reading."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import polars as pl

from packages.contracts import ResourcePolicy, ResourceRiskEstimate


def estimate_resource_risk(
    *,
    file_size_bytes: int,
    estimated_rows: int,
    column_count: int,
    available_memory_bytes: int,
    policy: ResourcePolicy | None = None,
) -> ResourceRiskEstimate:
    active = policy or ResourcePolicy()
    cells = estimated_rows * column_count
    estimated_memory = max(file_size_bytes * 3, cells * 24)
    warnings: list[str] = []
    risk = "low"
    if file_size_bytes > active.warning_file_size_bytes:
        warnings.append("File exceeds the configured size warning threshold")
        risk = "warning"
    if cells > active.maximum_estimated_cells:
        warnings.append("Estimated cells exceed the configured in-memory table warning threshold")
        risk = "warning"
    if estimated_memory > available_memory_bytes * active.memory_risk_ratio:
        warnings.append("Estimated processing memory exceeds the configured available-memory ratio")
        risk = "warning"
    if file_size_bytes > active.maximum_file_size_bytes or estimated_memory > available_memory_bytes:
        warnings.append("Execution is blocked before likely system instability")
        risk = "block"
    action = {
        "low": "Proceed with bounded preview and normal monitoring",
        "warning": "Use CSV batching, reduce profile limits, or split the source before full execution",
        "block": "Refuse full in-memory execution; split or convert the source and retry",
    }[risk]
    return ResourceRiskEstimate(
        file_size_bytes=file_size_bytes,
        estimated_rows=estimated_rows,
        column_count=column_count,
        estimated_cells=cells,
        estimated_peak_memory_bytes=estimated_memory,
        available_memory_bytes=available_memory_bytes,
        risk_level=risk,
        warnings=warnings,
        recommended_action=action,
    )


def iter_csv_batches(path: Path, batch_rows: int = 50_000) -> Iterator[pl.DataFrame]:
    if batch_rows < 1:
        raise ValueError("batch_rows must be positive")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            return
        records: list[dict[str, str | None]] = []
        for row in reader:
            records.append(row)
            if len(records) == batch_rows:
                yield pl.DataFrame(records, schema={name: pl.String for name in reader.fieldnames})
                records = []
        if records:
            yield pl.DataFrame(records, schema={name: pl.String for name in reader.fieldnames})
