from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import polars as pl

from packages.contracts import (
    CanonicalField,
    ColumnMapping,
    DiscoveryOverrides,
    ExtraFieldPolicy,
    FolderScanConfiguration,
    MappingSet,
    MissingRequiredPolicy,
    SchemaAlignmentPlan,
    SourceAlignmentConfiguration,
    SourceHandle,
)
from packages.data_engine.discovery import discover_source
from packages.data_engine.multi_source import build_batch_catalog, scan_folder_paths
from packages.data_engine.safety import Workspace
from packages.data_engine.schema_alignment import align_table, build_alignment_matrix


def _handle(workspace: Workspace, project_id, path: Path) -> tuple[SourceHandle, object]:  # type: ignore[no-untyped-def]
    source = workspace.import_source(path, path.name)
    handle = SourceHandle(
        id=source.id,
        project_id=project_id,
        original_filename=path.name,
        media_type="text/csv",
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    return handle, source


def test_folder_scan_patterns_recursive_fingerprints_and_limits(tmp_path: Path) -> None:
    root = tmp_path / "folder"
    (root / "nested").mkdir(parents=True)
    (root / "include.csv").write_text("id,value\n1,a\n", encoding="utf-8")
    (root / "skip.tmp.csv").write_text("id,value\n2,b\n", encoding="utf-8")
    (root / "nested" / "include.xlsx").write_bytes(b"synthetic-not-opened")
    (root / "note.txt").write_text("unsupported", encoding="utf-8")
    found = scan_folder_paths(
        FolderScanConfiguration(
            root_path=str(root),
            recursive=True,
            include_patterns=["*.csv", "nested/*.xlsx"],
            exclude_patterns=["*.tmp.csv"],
        )
    )
    assert [item.relative_path for item in found] == ["include.csv", "nested/include.xlsx"]
    assert all(len(item.fingerprint) == 64 for item in found)


def test_catalog_detects_duplicate_and_incremental_files(tmp_path: Path) -> None:
    project_id = uuid4()
    workspace = Workspace(tmp_path / "workspace")
    first_path = tmp_path / "a.csv"
    second_path = tmp_path / "b.csv"
    third_path = tmp_path / "c.csv"
    first_path.write_text("ID,Amount\n001,10\n", encoding="utf-8")
    second_path.write_text(first_path.read_text(encoding="utf-8"), encoding="utf-8")
    third_path.write_text("ID,Amount\n002,20\n", encoding="utf-8")
    first = _handle(workspace, project_id, first_path)
    second = _handle(workspace, project_id, second_path)
    third = _handle(workspace, project_id, third_path)
    catalog = build_batch_catalog(
        project_id,
        [first, second, third],  # type: ignore[list-item]
        DiscoveryOverrides(),
        previous_fingerprints={third[0].sha256},
    )
    assert catalog.files_considered == 3
    assert catalog.files_eligible == 1
    assert catalog.files_duplicate == 1
    assert catalog.files_unchanged == 1


def test_catalog_quarantines_failed_file_without_losing_eligible_sources(tmp_path: Path) -> None:
    project_id = uuid4()
    workspace = Workspace(tmp_path / "workspace")
    valid_path = tmp_path / "valid.csv"
    broken_path = tmp_path / "broken.xlsx"
    valid_path.write_text("id,value\n1,a\n", encoding="utf-8")
    broken_path.write_bytes(b"not-an-ooxml-workbook")
    valid = _handle(workspace, project_id, valid_path)
    broken = _handle(workspace, project_id, broken_path)
    catalog = build_batch_catalog(
        project_id,
        [valid, broken],  # type: ignore[list-item]
        DiscoveryOverrides(),
    )
    assert catalog.files_eligible == 1
    assert catalog.files_quarantined == 1
    assert next(item for item in catalog.items if item.filename == "broken.xlsx").state == "quarantined"


def test_catalog_honours_explicit_table_selection(fixture_dir: Path, tmp_path: Path) -> None:
    project_id = uuid4()
    workspace = Workspace(tmp_path / "workspace")
    handle, source = _handle(workspace, project_id, fixture_dir / "multiple_tables_rows.xlsx")
    discovery = discover_source(source, handle, DiscoveryOverrides())
    assert len(discovery.tables) >= 2
    selected = discovery.tables[1]
    catalog = build_batch_catalog(
        project_id,
        [(handle, source)],
        DiscoveryOverrides(),
        table_strategy="explicit",
        explicit_table_ids={handle.id: selected.table_id},
    )
    assert catalog.items[0].table_id == selected.table_id


def test_alignment_matrix_blocks_required_missing_and_reports_extras(tmp_path: Path) -> None:
    project_id = uuid4()
    workspace = Workspace(tmp_path / "workspace")
    source_path = tmp_path / "source.csv"
    source_path.write_text("Employee,Unexpected\n001,x\n", encoding="utf-8")
    handle, source = _handle(workspace, project_id, source_path)
    catalog = build_batch_catalog(
        project_id,
        [(handle, source)],  # type: ignore[list-item]
        DiscoveryOverrides(),
    )
    fields = [
        CanonicalField(id="employee_id", label="Employee", required=True),
        CanonicalField(id="amount", label="Amount", data_type="decimal", required=True),
    ]
    mapping = MappingSet(
        canonical_fields=fields,
        mappings=[ColumnMapping(source_column="Employee", canonical_field_id="employee_id")],
    )
    plan = SchemaAlignmentPlan(
        canonical_fields=fields,
        sources=[SourceAlignmentConfiguration(source_id=handle.id, mapping=mapping)],
        required_missing_policy=MissingRequiredPolicy.BLOCK_BATCH,
    )
    matrix = build_alignment_matrix(catalog, plan)
    assert matrix.blocked
    assert any(cell.status == "missing_required" and cell.canonical_field_id == "amount" for cell in matrix.cells)
    assert any(cell.status == "extra" and cell.source_field == "Unexpected" for cell in matrix.cells)


def test_incompatible_conversion_requires_explicit_user_acceptance(tmp_path: Path) -> None:
    project_id = uuid4()
    workspace = Workspace(tmp_path / "workspace")
    source_path = tmp_path / "source.csv"
    source_path.write_text("Amount\nnot-a-number\n", encoding="utf-8")
    handle, source = _handle(workspace, project_id, source_path)
    catalog = build_batch_catalog(project_id, [(handle, source)], DiscoveryOverrides())  # type: ignore[list-item]
    fields = [CanonicalField(id="amount", label="Amount", data_type="decimal")]
    mapping = MappingSet(
        canonical_fields=fields,
        mappings=[ColumnMapping(source_column="Amount", canonical_field_id="amount")],
    )
    unapproved = SchemaAlignmentPlan(
        canonical_fields=fields,
        sources=[SourceAlignmentConfiguration(source_id=handle.id, mapping=mapping)],
    )
    approved = unapproved.model_copy(
        update={
            "sources": [
                SourceAlignmentConfiguration(
                    source_id=handle.id,
                    mapping=mapping,
                    user_decisions={"amount": "accept"},
                )
            ]
        }
    )
    assert build_alignment_matrix(catalog, unapproved).blocked
    assert not build_alignment_matrix(catalog, approved).blocked


def test_alignment_can_include_extra_fields_with_stable_safe_ids() -> None:
    source_id = uuid4()
    fields = [CanonicalField(id="employee_id", label="Employee ID")]
    mapping = MappingSet(
        canonical_fields=fields,
        mappings=[ColumnMapping(source_column="Employee ID", canonical_field_id="employee_id")],
    )
    plan = SchemaAlignmentPlan(
        canonical_fields=fields,
        sources=[SourceAlignmentConfiguration(source_id=source_id, mapping=mapping)],
        extra_field_policy=ExtraFieldPolicy.INCLUDE,
    )
    aligned = align_table(
        table=pl.DataFrame({"Employee ID": ["E001"], "Unexpected Notes": ["review"], "__row_id": [1]}),
        source_id=source_id,
        source_filename="source.csv",
        source_table_id="table-1",
        plan=plan,
    )
    assert aligned["unexpected_notes"].to_list() == ["review"]
