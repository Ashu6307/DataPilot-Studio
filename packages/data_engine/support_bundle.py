"""User-previewed, recursively sanitised support bundle export."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.contracts import RunRecord, SupportBundleEntry, SupportBundlePreview

SECRET_KEY = re.compile(
    r"(password|passwd|secret|api[_-]?key|token|cookie|authorization|credential|private[_-]?key)",
    re.I,
)
ROW_PAYLOAD_KEY = re.compile(r"^(rows?|source_rows|rejected_rows|sample_values|preview|raw_data|payload)$", re.I)
SECRET_VALUE = re.compile(r"(?:^sk-|^ghp_|^xox[baprs]-|^Bearer\s+|-----BEGIN .*PRIVATE KEY-----)", re.I)
WINDOWS_USER_PATH = re.compile(r"[A-Za-z]:\\Users\\[^\\/]+", re.I)


def sanitise_support_value(value: Any, path: str = "root") -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if SECRET_KEY.search(key_text):
                result[key_text] = "[REDACTED_SECRET]"
            elif ROW_PAYLOAD_KEY.fullmatch(key_text):
                result[key_text] = "[EXCLUDED_SOURCE_ROWS]"
            else:
                result[key_text] = sanitise_support_value(child, f"{path}.{key_text}")
        return result
    if isinstance(value, list):
        return [sanitise_support_value(item, f"{path}[]") for item in value]
    if isinstance(value, str):
        if SECRET_VALUE.search(value):
            return "[REDACTED_SECRET]"
        return WINDOWS_USER_PATH.sub("[USER_HOME]", value)
    return value


def _serialise(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, default=str).encode("utf-8")


def build_support_bundle_preview(
    *,
    product_version: str,
    operating_system: str,
    dependencies: dict[str, str],
    configuration: dict[str, Any],
    runs: list[RunRecord],
    logs: list[dict[str, Any]],
    test_diagnostics: dict[str, Any],
    screenshot_paths: list[Path] | None = None,
) -> SupportBundlePreview:
    payloads = {
        "environment.json": sanitise_support_value(
            {
                "product_version": product_version,
                "operating_system": operating_system,
                "dependencies": dependencies,
            }
        ),
        "configuration.json": sanitise_support_value(configuration),
        "runs.json": sanitise_support_value(
            [
                {
                    "id": str(run.id),
                    "workflow_id": str(run.workflow_id),
                    "workflow_version": run.workflow_version,
                    "status": run.status,
                    "counts": {
                        "rows_read": run.rows_read,
                        "rows_written": run.rows_written,
                        "rows_rejected": run.rows_rejected,
                        "rows_filtered": run.rows_filtered,
                        "rows_aggregated": run.rows_aggregated,
                    },
                    "duration_ms": run.duration_ms,
                    "warnings": run.warnings,
                    "errors": run.errors,
                }
                for run in runs
            ]
        ),
        "logs.json": sanitise_support_value(logs),
        "test-diagnostics.json": sanitise_support_value(test_diagnostics),
    }
    entries = [
        SupportBundleEntry(
            path=name,
            category=name.removesuffix(".json"),
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        for name, payload in payloads.items()
        if (content := _serialise(payload))
    ]
    screenshots = [path.name for path in screenshot_paths or []]
    return SupportBundlePreview(
        entries=entries,
        sanitised_payloads=payloads,
        excluded_by_default=[
            "complete source rows and files",
            "passwords, tokens, API keys, cookies, and credential values",
            "unmasked sensitive values and absolute user-home paths",
            "screenshots unless separately approved",
        ],
        screenshots_requested=screenshots,
    )


def export_support_bundle(
    preview: SupportBundlePreview,
    destination_directory: Path,
    *,
    user_approved: bool,
    approved_screenshots: list[Path] | None = None,
) -> Path:
    if not user_approved:
        raise PermissionError("SUPPORT_BUNDLE_USER_APPROVAL_REQUIRED")
    destination_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    destination = destination_directory / f"datapilot-support-{stamp}-{str(preview.bundle_id)[:8]}.zip"
    payloads = sanitise_support_value(preview.sanitised_payloads)
    manifest: dict[str, Any] = {
        "bundle_id": str(preview.bundle_id),
        "created_at": preview.created_at.isoformat(),
        "entries": [],
        "excluded_by_default": preview.excluded_by_default,
    }
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in payloads.items():
            content = _serialise(payload)
            archive.writestr(name, content)
            manifest["entries"].append(
                {"path": name, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            )
        requested = set(preview.screenshots_requested)
        for screenshot in approved_screenshots or []:
            if screenshot.name not in requested:
                raise PermissionError("SCREENSHOT_NOT_PRESENT_IN_APPROVED_PREVIEW")
            archive.write(screenshot, f"screenshots/{screenshot.name}")
        archive.writestr("manifest.json", _serialise(manifest))
    return destination
