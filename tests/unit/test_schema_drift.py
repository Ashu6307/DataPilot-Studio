from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from packages.contracts import (
    CanonicalField,
    CanonicalType,
    ColumnMapping,
    DiscoveryOverrides,
    DriftCategory,
    DriftPolicy,
    DriftPolicyMode,
    MappingRepairAction,
    MappingRepairDecision,
    MappingSet,
    SchemaExpectation,
    SourceHandle,
)
from packages.data_engine.discovery import discover_source
from packages.data_engine.safety import Workspace
from packages.data_engine.schema_drift import analyze_schema_drift, repair_mapping


def _table(path: Path, tmp_path: Path):
    source = Workspace(tmp_path / "ws").import_source(path, path.name)
    handle = SourceHandle(
        id=source.id,
        project_id=uuid4(),
        original_filename=path.name,
        media_type="text/csv",
        size_bytes=source.size_bytes,
        sha256=source.sha256,
    )
    return discover_source(source, handle, DiscoveryOverrides()).tables[0]


def _mapping() -> MappingSet:
    return MappingSet(
        canonical_fields=[
            CanonicalField(
                id="employee_id",
                label="Employee ID",
                data_type=CanonicalType.TEXT,
                required=True,
                nullable=False,
                aliases=["Staff ID"],
            ),
            CanonicalField(id="full_name", label="Full Name", required=True, aliases=["Employee Name"]),
            CanonicalField(id="hours", label="Hours", data_type=CanonicalType.DECIMAL),
            CanonicalField(id="optional_note", label="Optional Note"),
        ],
        mappings=[
            ColumnMapping(source_column="Employee Code", canonical_field_id="employee_id"),
            ColumnMapping(source_column="Full Name", canonical_field_id="full_name"),
            ColumnMapping(source_column="Hours", canonical_field_id="hours"),
            ColumnMapping(source_column="Note", canonical_field_id="optional_note"),
        ],
    )


def test_classifies_reorder_rename_add_remove_and_type_drift(fixture_dir: Path, tmp_path: Path) -> None:
    observed = _table(fixture_dir / "renamed_columns.csv", tmp_path)
    result = analyze_schema_drift(
        SchemaExpectation(mapping=_mapping(), approved_synonyms={"hours": ["Worked Hours"]}),
        observed,
    )
    categories = {item.category for item in result.findings}
    assert DriftCategory.COLUMN_RENAMED in categories
    assert DriftCategory.OPTIONAL_COLUMN_REMOVED in categories
    assert DriftCategory.COLUMN_ADDED in categories
    assert result.requires_confirmation
    assert result.candidates["employee_id"][0].source_column == "Staff ID"


def test_safe_policy_only_auto_accepts_unique_high_confidence(fixture_dir: Path, tmp_path: Path) -> None:
    observed = _table(fixture_dir / "reordered_columns.csv", tmp_path)
    result = analyze_schema_drift(
        SchemaExpectation(mapping=_mapping()),
        observed,
        DriftPolicy(mode=DriftPolicyMode.AUTO_ACCEPT_SAFE),
    )
    assert result.auto_accepted["employee_id"] == "Employee Code"
    assert "optional_note" not in result.auto_accepted
    assert any(item.category == DriftCategory.COLUMN_REORDERED for item in result.findings)


def test_low_confidence_or_ambiguous_mapping_blocks() -> None:
    from packages.contracts import ColumnProfile, TableDiscovery

    table = TableDiscovery(
        table_id="table",
        sheet_name="sheet",
        candidate_region="A1:B2",
        candidate_headers=[],
        selected_header_row=1,
        selected_header_rows=[1],
        row_count_estimate=1,
        column_count=2,
        blank_leading_rows=0,
        blank_trailing_rows=0,
        columns=[
            ColumnProfile(
                source_name="Employee Ref A",
                inferred_type="text",
                null_percentage=0,
                unique_count=1,
                duplicate_count=0,
                sample_values=["001"],
            ),
            ColumnProfile(
                source_name="Employee Ref B",
                inferred_type="text",
                null_percentage=0,
                unique_count=1,
                duplicate_count=0,
                sample_values=["002"],
            ),
        ],
        preview=[],
        confidence=1,
    )
    result = analyze_schema_drift(SchemaExpectation(mapping=_mapping()), table)
    assert result.blocked
    assert any(item.category == DriftCategory.AMBIGUOUS_MAPPING for item in result.findings)


def test_user_repair_creates_new_mapping_version_and_audit() -> None:
    mapping = _mapping()
    repaired, audit = repair_mapping(
        mapping,
        [
            MappingRepairDecision(
                canonical_field_id="employee_id",
                action=MappingRepairAction.ACCEPT,
                selected_source_column="Staff ID",
                suggestion_confidence=0.98,
            )
        ],
    )
    assert mapping.version == 1
    assert repaired.version == 2
    assert repaired.mappings[0].source_column == "Staff ID"
    assert repaired.mappings[0].user_confirmed
    assert audit.previous_mapping_version == 1
    assert audit.repaired_mapping_version == 2
