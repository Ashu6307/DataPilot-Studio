"""Measured synthetic benchmarks for Milestone 2B safety budgets."""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl

from packages.contracts import (
    BlockingMethod,
    CandidateConstraint,
    ComparisonConfiguration,
    FuzzyFieldConfiguration,
    FuzzyMethod,
    MatchMethod,
    MatchStage,
    NumericTolerance,
    NumericToleranceMode,
    ReconciliationWorkflow,
)
from packages.data_engine.comparison import compare_datasets
from packages.data_engine.reconciliation import reconcile_datasets
from packages.data_engine.reconciliation_exporter import export_reconciliation_evidence


def measure(name: str, rows: int, operation: Callable[[], Any]) -> tuple[dict[str, Any], Any]:
    tracemalloc.start()
    started = time.perf_counter()
    result = operation()
    duration = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {
        "scenario": name,
        "rows_per_side": rows,
        "duration_seconds": round(duration, 6),
        "python_peak_bytes": peak,
    }, result


def exact_comparison(rows: int) -> tuple[dict[str, Any], Any]:
    left_id, right_id = uuid4(), uuid4()
    left = pl.DataFrame({"key": [f"K{index:07d}" for index in range(rows)], "value": range(rows)})
    right = pl.DataFrame({"value": range(rows), "key": [f"K{index:07d}" for index in range(rows)]})
    config = ComparisonConfiguration(
        project_id=uuid4(),
        left_dataset_id=left_id,
        right_dataset_id=right_id,
        business_key_fields=["key"],
        compare_fields=["value"],
    )
    metric, result = measure("exact_comparison", rows, lambda: compare_datasets(left, right, config))
    metric["output_counts"] = result.summary.model_dump(mode="json")
    metric["candidate_pairs"] = rows
    return metric, result


def fuzzy_and_review(rows: int) -> tuple[dict[str, Any], Any]:
    left_id, right_id = uuid4(), uuid4()
    left = pl.DataFrame(
        {"block": [f"B{index:06d}" for index in range(rows)], "name": [f"alpha unit {index}" for index in range(rows)]}
    )
    right = pl.DataFrame(
        {
            "block": [f"B{index:06d}" for index in range(rows) for _ in range(2)],
            "name": [f"unit alpha {index}" for index in range(rows) for _ in range(2)],
        }
    )
    workflow = ReconciliationWorkflow(
        project_id=uuid4(),
        display_name="Synthetic blocked fuzzy benchmark",
        left_dataset_id=left_id,
        right_dataset_id=right_id,
        evidence_fields=["block", "name"],
        stages=[
            MatchStage(
                id="blocked_fuzzy",
                name="Blocked fuzzy",
                priority=1,
                left_key_fields=["name"],
                right_key_fields=["name"],
                method=MatchMethod.FUZZY_TEXT,
                threshold="0.7",
                candidate_constraints=[
                    CandidateConstraint(
                        id="same_block",
                        method=BlockingMethod.EXACT,
                        left_field="block",
                        right_field="block",
                    )
                ],
                fuzzy_fields=[
                    FuzzyFieldConfiguration(
                        left_field="name",
                        right_field="name",
                        method=FuzzyMethod.TOKEN_SORT,
                        threshold="0.7",
                    )
                ],
            )
        ],
    )
    metric, result = measure("candidate_blocked_fuzzy_review", rows, lambda: reconcile_datasets(left, right, workflow))
    metric["candidate_pairs"] = result.stage_estimates[0].estimated_pairs
    metric["output_counts"] = result.summary.model_dump(mode="json")
    return metric, (workflow, result)


def tolerance_matching(rows: int) -> tuple[dict[str, Any], Any]:
    left_id, right_id = uuid4(), uuid4()
    left = pl.DataFrame(
        {
            "block": [f"B{index:07d}" for index in range(rows)],
            "amount": [f"{index}.00" for index in range(rows)],
        }
    )
    right = pl.DataFrame(
        {
            "block": [f"B{index:07d}" for index in range(rows)],
            "amount": [f"{index}.01" for index in range(rows)],
        }
    )
    workflow = ReconciliationWorkflow(
        project_id=uuid4(),
        display_name="Synthetic tolerance benchmark",
        left_dataset_id=left_id,
        right_dataset_id=right_id,
        stages=[
            MatchStage(
                id="amount_tolerance",
                name="Amount tolerance",
                priority=1,
                left_key_fields=["amount"],
                right_key_fields=["amount"],
                method=MatchMethod.NUMERIC_TOLERANCE,
                threshold="0.8",
                numeric_tolerances={
                    "amount": NumericTolerance(
                        mode=NumericToleranceMode.CURRENCY,
                        tolerance="0.05",
                    )
                },
                candidate_constraints=[
                    CandidateConstraint(
                        id="same_block",
                        method=BlockingMethod.EXACT,
                        left_field="block",
                        right_field="block",
                    )
                ],
            )
        ],
    )
    metric, result = measure("blocked_numeric_tolerance", rows, lambda: reconcile_datasets(left, right, workflow))
    metric["candidate_pairs"] = result.stage_estimates[0].estimated_pairs
    metric["output_counts"] = result.summary.model_dump(mode="json")
    return metric, result


def duplicate_groups(rows: int) -> tuple[dict[str, Any], Any]:
    left_id, right_id = uuid4(), uuid4()
    left = pl.DataFrame({"key": ["DUPLICATE"] * rows, "value": range(rows)})
    right = pl.DataFrame({"key": ["DUPLICATE"] * rows, "value": range(rows)})
    config = ComparisonConfiguration(
        project_id=uuid4(),
        left_dataset_id=left_id,
        right_dataset_id=right_id,
        business_key_fields=["key"],
        compare_fields=["value"],
    )
    metric, result = measure("large_duplicate_key_group", rows, lambda: compare_datasets(left, right, config))
    metric["candidate_pairs"] = 0
    metric["output_counts"] = result.summary.model_dump(mode="json")
    return metric, result


def export_benchmark(workflow: ReconciliationWorkflow, result: Any, root: Path) -> dict[str, Any]:
    destination = root / "m2b-export"
    metric, manifest = measure(
        "excel_csv_json_zip_export",
        result.summary.total_left_rows,
        lambda: export_reconciliation_evidence(destination, result, workflow),
    )
    metric["candidate_pairs"] = sum(item.estimated_pairs for item in result.stage_estimates)
    metric["output_counts"] = manifest.output_counts
    metric["artifact_bytes"] = sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
    return metric


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Use small CI-safe sizes")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--export-root", type=Path, default=Path(".datapilot/benchmarks"))
    args = parser.parse_args()
    exact_sizes = [1_000, 5_000] if args.quick else [10_000, 100_000]
    fuzzy_size = 100 if args.quick else 2_000
    tolerance_size = 500 if args.quick else 10_000
    duplicate_size = 500 if args.quick else 10_000
    results: list[dict[str, Any]] = []
    for size in exact_sizes:
        metric, _ = exact_comparison(size)
        results.append(metric)
    fuzzy_metric, (workflow, fuzzy_result) = fuzzy_and_review(fuzzy_size)
    results.append(fuzzy_metric)
    tolerance_metric, _ = tolerance_matching(tolerance_size)
    results.append(tolerance_metric)
    duplicate_metric, _ = duplicate_groups(duplicate_size)
    results.append(duplicate_metric)
    args.export_root.mkdir(parents=True, exist_ok=True)
    results.append(export_benchmark(workflow, fuzzy_result, args.export_root))
    payload = {
        "hardware": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "machine": platform.machine(),
            "logical_cores": os.cpu_count(),
            "python": platform.python_version(),
        },
        "input_characteristics": "synthetic canonical text keys; fuzzy candidates blocked to two per left row",
        "results": results,
        "limitations": [
            "tracemalloc reports Python allocations, not complete process RSS or native Polars allocations",
            "fuzzy measurement is candidate-blocked and is not an all-to-all scalability claim",
        ],
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
