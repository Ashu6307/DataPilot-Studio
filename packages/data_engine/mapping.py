"""Source-label to canonical-field resolution."""

from __future__ import annotations

from typing import Any

import polars as pl

from packages.contracts import MappingSet


def apply_mapping(table: pl.DataFrame, mapping_set: MappingSet) -> pl.DataFrame:
    expressions: list[pl.Expr] = []
    available = set(table.columns)
    for mapping in mapping_set.mappings:
        target = mapping.canonical_field_id
        if mapping.source_column is not None:
            if mapping.source_column not in available:
                field = next(item for item in mapping_set.canonical_fields if item.id == target)
                alias_match = next((alias for alias in field.aliases if alias in available), None)
                if alias_match is None:
                    if mapping.default_value is not None:
                        expressions.append(pl.lit(_as_text(mapping.default_value)).alias(target))
                        continue
                    if field.required:
                        raise ValueError(f"MAPPING_REQUIRED_SOURCE_MISSING: {mapping.source_column}")
                    expressions.append(pl.lit(None, dtype=pl.String).alias(target))
                    continue
                source_column = alias_match
            else:
                source_column = mapping.source_column
            expression = pl.col(source_column).cast(pl.String, strict=False)
            if mapping.default_value is not None:
                expression = pl.when(expression.is_null() | (expression == "")).then(
                    pl.lit(_as_text(mapping.default_value))
                ).otherwise(expression)
            expressions.append(expression.alias(target))
        else:
            value = mapping.constant_value if mapping.constant_value is not None else mapping.default_value
            expressions.append(pl.lit(_as_text(value)).alias(target))
    mapped = table.select(expressions) if expressions else pl.DataFrame()
    return mapped.with_row_index("__row_id", offset=1)


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value)

