from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest

from packages.contracts import RunRecord, RunStatus
from packages.data_engine.support_bundle import build_support_bundle_preview, export_support_bundle


def test_support_bundle_requires_preview_approval_and_redacts_sensitive_data(tmp_path: Path) -> None:
    run = RunRecord(
        project_id=uuid4(),
        workflow_id=uuid4(),
        workflow_version=1,
        status=RunStatus.FAILED,
        source_filename="private-source.csv",
        source_fingerprint="a" * 64,
        rows_read=4,
        rows_written=0,
        errors=["CORRELATION-123"],
    )
    preview = build_support_bundle_preview(
        product_version="0.2.0",
        operating_system="Windows",
        dependencies={"python": "3.14.0"},
        configuration={
            "api_key": "sk-real-looking-secret",
            "workspace": r"C:\Users\ashum\private",
            "preview": [{"employee_id": "00124", "name": "Private Person"}],
        },
        runs=[run],
        logs=[{"message": "failed", "token": "Bearer abc", "source_rows": [{"secret": "value"}]}],
        test_diagnostics={"pytest": "passed"},
    )
    serialised = json.dumps(preview.sanitised_payloads)
    assert "sk-real-looking-secret" not in serialised
    assert "Private Person" not in serialised
    assert r"C:\\Users\\ashum" not in serialised
    assert "[REDACTED_SECRET]" in serialised
    assert "[EXCLUDED_SOURCE_ROWS]" in serialised
    with pytest.raises(PermissionError, match="USER_APPROVAL_REQUIRED"):
        export_support_bundle(preview, tmp_path, user_approved=False)

    bundle = export_support_bundle(preview, tmp_path, user_approved=True)
    with zipfile.ZipFile(bundle) as archive:
        assert "manifest.json" in archive.namelist()
        payload = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist())
        assert "sk-real-looking-secret" not in payload
        assert "Private Person" not in payload
        assert "rows_read" in payload


def test_unpreviewed_screenshot_cannot_be_added(tmp_path: Path) -> None:
    screenshot = tmp_path / "screen.png"
    screenshot.write_bytes(b"not-real-image")
    preview = build_support_bundle_preview(
        product_version="0.2.0",
        operating_system="Windows",
        dependencies={},
        configuration={},
        runs=[],
        logs=[],
        test_diagnostics={},
    )
    with pytest.raises(PermissionError, match="SCREENSHOT_NOT_PRESENT"):
        export_support_bundle(
            preview,
            tmp_path / "bundles",
            user_approved=True,
            approved_screenshots=[screenshot],
        )
