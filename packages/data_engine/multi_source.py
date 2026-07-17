"""Read-only folder scanning and per-file discovery for composition batches."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException

from packages.contracts import (
    BatchCatalog,
    BatchSourceItem,
    BatchSourceState,
    CanonicalField,
    DiscoveryOverrides,
    FolderScanConfiguration,
    SourceHandle,
    TableDiscovery,
)
from packages.data_engine.discovery import discover_source
from packages.data_engine.safety import SourceFile, sha256_file


@dataclass(frozen=True, slots=True)
class FolderPathCandidate:
    path: Path
    relative_path: str
    fingerprint: str
    size_bytes: int


def scan_folder_paths(configuration: FolderScanConfiguration) -> list[FolderPathCandidate]:
    root = Path(configuration.root_path).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"FOLDER_NOT_FOUND: {root}")
    iterator = root.rglob("*") if configuration.recursive else root.glob("*")
    candidates: list[FolderPathCandidate] = []
    for path in sorted((item for item in iterator if item.is_file()), key=lambda item: item.as_posix().casefold()):
        relative = path.relative_to(root).as_posix()
        if path.suffix.casefold() not in configuration.supported_extensions:
            continue
        if not any(fnmatch.fnmatch(relative, pattern) for pattern in configuration.include_patterns):
            continue
        if any(fnmatch.fnmatch(relative, pattern) for pattern in configuration.exclude_patterns):
            continue
        candidates.append(FolderPathCandidate(path, relative, sha256_file(path), path.stat().st_size))
        if len(candidates) >= configuration.maximum_files:
            break
    return candidates


def _field_id(label: str, used: set[str]) -> str:
    import re

    value = re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_") or "field"
    if value[0].isdigit():
        value = f"field_{value}"
    candidate = value[:72]
    suffix = 2
    while candidate in used:
        candidate = f"{value[:68]}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _select_table(
    discovery_tables: list[TableDiscovery],
    strategy: str,
    explicit_table_id: str | None = None,
) -> TableDiscovery | None:
    if not discovery_tables:
        return None
    if explicit_table_id is not None:
        selected = next((item for item in discovery_tables if item.table_id == explicit_table_id), None)
        if selected is None:
            raise ValueError(f"EXPLICIT_TABLE_ID_NOT_FOUND: {explicit_table_id}")
        return selected
    if strategy == "explicit":
        raise ValueError("EXPLICIT_TABLE_ID_REQUIRED")
    if strategy == "largest":
        return max(discovery_tables, key=lambda item: (item.row_count_estimate, item.column_count))
    return next((item for item in discovery_tables if item.sheet_state == "visible"), discovery_tables[0])


def build_batch_catalog(
    project_id: UUID,
    sources: list[tuple[SourceHandle, SourceFile]],
    overrides: DiscoveryOverrides,
    table_strategy: str = "first_visible",
    previous_fingerprints: set[str] | None = None,
    relative_paths: dict[UUID, str] | None = None,
    explicit_table_ids: dict[UUID, str] | None = None,
) -> BatchCatalog:
    previous = previous_fingerprints or set()
    paths = relative_paths or {}
    explicit_tables = explicit_table_ids or {}
    seen: dict[str, UUID] = {}
    items: list[BatchSourceItem] = []
    for handle, source in sources:
        relative_path = paths.get(handle.id, handle.original_filename)
        suffix = Path(handle.original_filename).suffix.casefold().lstrip(".")
        duplicate_of = seen.get(handle.sha256)
        if duplicate_of is not None:
            items.append(
                BatchSourceItem(
                    source_id=handle.id,
                    filename=Path(handle.original_filename).name,
                    relative_path=relative_path,
                    fingerprint=handle.sha256,
                    file_type=suffix,
                    state=BatchSourceState.DUPLICATE,
                    processing_eligible=False,
                    duplicate_of=duplicate_of,
                    warnings=["Duplicate fingerprint; first catalog occurrence remains eligible"],
                )
            )
            continue
        seen[handle.sha256] = handle.id
        if handle.sha256 in previous:
            items.append(
                BatchSourceItem(
                    source_id=handle.id,
                    filename=Path(handle.original_filename).name,
                    relative_path=relative_path,
                    fingerprint=handle.sha256,
                    file_type=suffix,
                    state=BatchSourceState.UNCHANGED,
                    processing_eligible=False,
                    warnings=["Fingerprint already processed by the supplied incremental baseline"],
                )
            )
            continue
        try:
            discovery = discover_source(source, handle, overrides)
            table = _select_table(discovery.tables, table_strategy, explicit_tables.get(handle.id))
            if table is None:
                raise ValueError("NO_DISCOVERED_TABLE")
            used: set[str] = set()
            fields = [
                CanonicalField(
                    id=_field_id(column.source_name, used),
                    label=column.source_name,
                    data_type=column.inferred_type,
                    required=False,
                )
                for column in table.columns
            ]
            items.append(
                BatchSourceItem(
                    source_id=handle.id,
                    filename=Path(handle.original_filename).name,
                    relative_path=relative_path,
                    fingerprint=handle.sha256,
                    file_type=suffix,
                    table_id=table.table_id,
                    discovered_schema=fields,
                    discovery=table,
                    row_estimate=table.row_count_estimate,
                    warnings=[*discovery.warnings, *table.warnings],
                    state=BatchSourceState.ELIGIBLE,
                    processing_eligible=True,
                )
            )
        except (BadZipFile, EOFError, InvalidFileException, UnicodeError, ValueError, OSError, RuntimeError) as error:
            items.append(
                BatchSourceItem(
                    source_id=handle.id,
                    filename=Path(handle.original_filename).name,
                    relative_path=relative_path,
                    fingerprint=handle.sha256,
                    file_type=suffix,
                    state=BatchSourceState.QUARANTINED,
                    processing_eligible=False,
                    warnings=[f"SOURCE_DISCOVERY_FAILED: {type(error).__name__}"],
                )
            )
    return BatchCatalog(
        project_id=project_id,
        items=items,
        files_considered=len(items),
        files_eligible=sum(item.state == BatchSourceState.ELIGIBLE for item in items),
        files_duplicate=sum(item.state == BatchSourceState.DUPLICATE for item in items),
        files_unchanged=sum(item.state == BatchSourceState.UNCHANGED for item in items),
        files_quarantined=sum(item.state in {BatchSourceState.QUARANTINED, BatchSourceState.FAILED} for item in items),
        total_row_estimate=sum(item.row_estimate for item in items if item.processing_eligible),
        warnings=["Mixed source structures require explicit canonical alignment before composition"],
    )
