from __future__ import annotations

from pathlib import Path

from packages.contracts import ResourcePolicy
from packages.data_engine.resource_policy import estimate_resource_risk, iter_csv_batches


def test_resource_risk_warns_and_blocks_before_instability() -> None:
    policy = ResourcePolicy(
        warning_file_size_bytes=100,
        maximum_file_size_bytes=1_000,
        maximum_estimated_cells=100,
        memory_risk_ratio=0.25,
    )
    warning = estimate_resource_risk(
        file_size_bytes=200,
        estimated_rows=50,
        column_count=5,
        available_memory_bytes=10_000,
        policy=policy,
    )
    assert warning.risk_level == "warning"
    blocked = estimate_resource_risk(
        file_size_bytes=2_000,
        estimated_rows=1_000,
        column_count=20,
        available_memory_bytes=10_000,
        policy=policy,
    )
    assert blocked.risk_level == "block"
    assert "Refuse" in blocked.recommended_action


def test_csv_batches_are_bounded_and_preserve_identifier_text(
    fixture_dir: Path,
) -> None:
    batches = list(iter_csv_batches(fixture_dir / "large_synthetic_100k.csv", batch_rows=40_000))
    assert [batch.height for batch in batches] == [40_000, 40_000, 20_000]
    assert batches[0].get_column("Employee Code")[0] == "00000000"
    assert sum(batch.height for batch in batches) == 100_000
