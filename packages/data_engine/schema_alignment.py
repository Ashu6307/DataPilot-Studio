"""Canonical schema alignment matrix and safe table conversion."""

from __future__ import annotations

from uuid import UUID

import polars as pl
from polars.datatypes import DataTypeClass

from packages.contracts import (
    AlignmentCellStatus,
    AlignmentMatrixCell,
    BatchCatalog,
    CanonicalField,
    CanonicalType,
    ExtraFieldPolicy,
    MissingRequiredPolicy,
    SchemaAlignmentMatrix,
    SchemaAlignmentPlan,
)
from packages.data_engine.mapping import apply_mapping
from packages.shared_utils import slugify_field


def _compatible(source: CanonicalType, target: CanonicalType) -> bool:
    if source == target or target == CanonicalType.TEXT:
        return True
    return {source, target} <= {CanonicalType.INTEGER, CanonicalType.DECIMAL} or {
        source,
        target,
    } <= {CanonicalType.DATE, CanonicalType.DATETIME}


def _conversion(source: CanonicalType, target: CanonicalType) -> str:
    return "identity" if source == target else f"safe_cast:{source.value}->{target.value}"


def build_alignment_matrix(catalog: BatchCatalog, plan: SchemaAlignmentPlan) -> SchemaAlignmentMatrix:
    catalog_by_id = {item.source_id: item for item in catalog.items}
    cells: list[AlignmentMatrixCell] = []
    rejected: set[UUID] = set()
    quarantined: set[UUID] = set()
    blocked = False
    warnings: list[str] = []
    for source_plan in plan.sources:
        item = catalog_by_id.get(source_plan.source_id)
        if item is None or not item.processing_eligible or item.discovery is None:
            rejected.add(source_plan.source_id)
            warnings.append(f"Source {source_plan.source_id} is not eligible for alignment")
            continue
        observed = {column.source_name: column for column in item.discovery.columns}
        mapped_sources: set[str] = set()
        mapping_by_target = {mapping.canonical_field_id: mapping for mapping in source_plan.mapping.mappings}
        for field in plan.canonical_fields:
            mapping = mapping_by_target.get(field.id)
            status = AlignmentCellStatus.MISSING_OPTIONAL
            source_name: str | None = None
            confidence = 0.0
            source_type: CanonicalType | None = None
            conversion: str | None = None
            cell_warnings: list[str] = []
            if mapping is not None and mapping.source_column is not None:
                source_name = mapping.source_column
                profile = observed.get(source_name)
                if profile is None:
                    source_name = next(
                        (alias for alias in [field.label, *field.aliases] if alias in observed),
                        None,
                    )
                    profile = observed.get(source_name) if source_name else None
                if profile is not None:
                    mapped_sources.add(profile.source_name)
                    source_type = profile.inferred_type
                    confidence = mapping.confidence
                    conversion = _conversion(source_type, field.data_type)
                    status = AlignmentCellStatus.MAPPED
                    if not _compatible(source_type, field.data_type):
                        status = AlignmentCellStatus.TYPE_MISMATCH
                        cell_warnings.append("Observed and target types require an explicit reviewed conversion")
            elif mapping is not None and mapping.constant_value is not None:
                status = AlignmentCellStatus.CONSTANT
                confidence = 1.0
                conversion = "constant"
            elif mapping is not None and mapping.default_value is not None:
                status = AlignmentCellStatus.DEFAULTED
                confidence = 1.0
                conversion = "approved_default"
            if status == AlignmentCellStatus.MISSING_OPTIONAL and field.required:
                status = AlignmentCellStatus.MISSING_REQUIRED
                if plan.required_missing_policy == MissingRequiredPolicy.QUARANTINE_FILE:
                    quarantined.add(source_plan.source_id)
                elif plan.required_missing_policy == MissingRequiredPolicy.REJECT_FILE:
                    rejected.add(source_plan.source_id)
                else:
                    blocked = True
                cell_warnings.append("Required canonical field is unresolved")
            if status == AlignmentCellStatus.TYPE_MISMATCH and source_plan.user_decisions.get(field.id) != "accept":
                blocked = True
            cells.append(
                AlignmentMatrixCell(
                    canonical_field_id=field.id,
                    source_id=source_plan.source_id,
                    source_field=source_name,
                    confidence=confidence,
                    source_type=source_type,
                    target_type=field.data_type,
                    conversion=conversion,
                    status=status,
                    user_decision=source_plan.user_decisions.get(field.id),
                    warnings=cell_warnings,
                )
            )
        extras = set(observed) - mapped_sources
        for extra in sorted(extras):
            profile = observed[extra]
            cells.append(
                AlignmentMatrixCell(
                    canonical_field_id=None,
                    source_id=source_plan.source_id,
                    source_field=extra,
                    source_type=profile.inferred_type,
                    status=AlignmentCellStatus.EXTRA,
                    warnings=[f"Extra field policy: {plan.extra_field_policy.value}"],
                )
            )
            if plan.extra_field_policy == ExtraFieldPolicy.BLOCK:
                blocked = True
    eligible = [
        source.source_id
        for source in plan.sources
        if source.source_id not in rejected and source.source_id not in quarantined
    ]
    return SchemaAlignmentMatrix(
        plan_id=plan.id,
        plan_version=plan.version,
        cells=cells,
        eligible_source_ids=eligible,
        rejected_source_ids=sorted(rejected, key=str),
        quarantined_source_ids=sorted(quarantined, key=str),
        blocked=blocked,
        warnings=warnings,
    )


def _target_dtype(field: CanonicalField) -> DataTypeClass:
    return {
        CanonicalType.TEXT: pl.String,
        CanonicalType.INTEGER: pl.Int64,
        CanonicalType.DECIMAL: pl.Float64,
        CanonicalType.BOOLEAN: pl.Boolean,
        CanonicalType.DATE: pl.Date,
        CanonicalType.DATETIME: pl.Datetime,
    }[field.data_type]


def align_table(
    table: pl.DataFrame,
    source_id: UUID,
    source_filename: str,
    source_table_id: str,
    plan: SchemaAlignmentPlan,
) -> pl.DataFrame:
    source_plan = next((item for item in plan.sources if item.source_id == source_id), None)
    if source_plan is None:
        raise ValueError(f"ALIGNMENT_SOURCE_NOT_CONFIGURED: {source_id}")
    mapped = apply_mapping(table, source_plan.mapping)
    extra_fields: list[str] = []
    if plan.extra_field_policy == ExtraFieldPolicy.INCLUDE:
        mapped_sources = {
            mapping.source_column
            for mapping in source_plan.mapping.mappings
            if mapping.source_column is not None
        }
        used = {field.id for field in plan.canonical_fields}
        for source_column in table.columns:
            if source_column.startswith("__") or source_column in mapped_sources:
                continue
            output = slugify_field(source_column, "extra_field")
            if output in used:
                output = slugify_field(f"extra_{source_column}", "extra_field")
            suffix = 2
            candidate = output
            while candidate in used:
                candidate = f"{output[:75]}_{suffix}"
                suffix += 1
            used.add(candidate)
            extra_fields.append(candidate)
            mapped = mapped.with_columns(table[source_column].alias(candidate))
    expressions: list[pl.Expr] = []
    for field in plan.canonical_fields:
        if field.id not in mapped.columns:
            if field.required:
                raise ValueError(f"ALIGNMENT_REQUIRED_FIELD_MISSING: {field.id}")
            expressions.append(pl.lit(None, dtype=_target_dtype(field)).alias(field.id))
            continue
        expressions.append(pl.col(field.id).cast(_target_dtype(field), strict=False).alias(field.id))
    row_id = pl.col("__row_id").cast(pl.Int64).alias("__source_row")
    expressions.extend(pl.col(field) for field in extra_fields)
    return mapped.select(expressions + [row_id]).with_columns(
        pl.lit(str(source_id)).alias("__source_id"),
        pl.lit(source_filename).alias("__source_file"),
        pl.lit(source_table_id).alias("__source_table"),
    )
