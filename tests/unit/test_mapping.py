from __future__ import annotations

import polars as pl

from packages.contracts import CanonicalField, ColumnMapping, MappingSet
from packages.data_engine.mapping import apply_mapping


def test_mapping_is_name_based_and_uses_aliases() -> None:
    table = pl.DataFrame({"Employee Name": ["A"], "Staff ID": ["0012"]})
    mapping = MappingSet(
        canonical_fields=[
            CanonicalField(id="employee_id", label="ID", required=True, aliases=["Staff ID"]),
            CanonicalField(id="name", label="Name", aliases=["Employee Name"]),
        ],
        mappings=[
            ColumnMapping(source_column="Employee Code", canonical_field_id="employee_id"),
            ColumnMapping(source_column="Full Name", canonical_field_id="name"),
        ],
    )
    result = apply_mapping(table.select(["Staff ID", "Employee Name"]), mapping)
    assert result.select(["employee_id", "name"]).to_dicts() == [{"employee_id": "0012", "name": "A"}]


def test_mapping_supports_constant_and_default() -> None:
    table = pl.DataFrame({"Name": ["", "B"]})
    mapping = MappingSet(
        canonical_fields=[
            CanonicalField(id="name", label="Name"),
            CanonicalField(id="source", label="Source"),
        ],
        mappings=[
            ColumnMapping(source_column="Name", canonical_field_id="name", default_value="Unknown"),
            ColumnMapping(canonical_field_id="source", constant_value="upload"),
        ],
    )
    result = apply_mapping(table, mapping)
    assert result.get_column("name").to_list() == ["Unknown", "B"]
    assert result.get_column("source").to_list() == ["upload", "upload"]

