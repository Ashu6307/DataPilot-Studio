from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from packages.contracts import DiscoveryOverrides, SourceHandle
from packages.data_engine import Workspace, discover_source


@pytest.mark.performance
def test_large_csv_discovery_is_bounded(fixture_dir: Path, tmp_path: Path) -> None:
    source = Workspace(tmp_path / "workspace").import_source(
        fixture_dir / "large_synthetic_100k.csv", "large_synthetic_100k.csv"
    )
    handle = SourceHandle(
        id=source.id,
        project_id=uuid4(),
        original_filename=source.original_filename,
        media_type="text/csv",
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    result = discover_source(source, handle, DiscoveryOverrides(preview_rows=20))
    assert len(result.tables[0].preview) == 20

