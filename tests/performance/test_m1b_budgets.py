from __future__ import annotations

import time
from pathlib import Path

from packages.contracts import DiscoveryOverrides
from packages.data_engine.discovery import read_selected_table
from packages.data_engine.resource_policy import iter_csv_batches
from packages.data_engine.safety import Workspace


def test_100k_csv_preview_is_bounded_and_batch_iteration_reconciles(
    fixture_dir: Path, tmp_path: Path
) -> None:
    path = fixture_dir / "large_synthetic_100k.csv"
    started = time.perf_counter()
    batches = list(iter_csv_batches(path, 25_000))
    assert sum(batch.height for batch in batches) == 100_000
    assert max(batch.height for batch in batches) <= 25_000
    source = Workspace(tmp_path / "workspace").import_source(path, path.name)
    preview = read_selected_table(source, DiscoveryOverrides(), limit=200)
    assert preview.height == 200
    assert time.perf_counter() - started < 30
