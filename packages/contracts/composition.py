"""Versioned contracts for generic multi-source data composition."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .models import (
    CanonicalField,
    CanonicalType,
    DiscoveryOverrides,
    ExpressionNode,
    MappingSet,
    RunStatus,
    StrictModel,
    TableDiscovery,
    utc_now,
)


class BatchSourceState(StrEnum):
    ELIGIBLE = "eligible"
    DUPLICATE = "duplicate"
    UNCHANGED = "unchanged"
    QUARANTINED = "quarantined"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


def _default_extensions() -> list[Literal[".csv", ".xlsx", ".xlsm"]]:
    return [".csv", ".xlsx", ".xlsm"]


class FolderScanConfiguration(StrictModel):
    root_path: str = Field(min_length=1, max_length=2_000)
    recursive: bool = False
    include_patterns: list[str] = Field(default_factory=lambda: ["*"])
    exclude_patterns: list[str] = Field(default_factory=list)
    supported_extensions: list[Literal[".csv", ".xlsx", ".xlsm"]] = Field(default_factory=_default_extensions)
    table_strategy: Literal["first_visible", "largest", "explicit"] = "first_visible"
    explicit_table_ids: dict[str, str] = Field(default_factory=dict)
    previous_fingerprints: list[str] = Field(default_factory=list)
    maximum_files: int = Field(default=5_000, ge=1, le=100_000)


class FolderScanRequest(StrictModel):
    project_id: UUID
    configuration: FolderScanConfiguration
    discovery_overrides: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)


class BatchCatalogRequest(StrictModel):
    project_id: UUID
    source_ids: list[UUID] = Field(min_length=1, max_length=5_000)
    discovery_overrides: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)
    table_strategy: Literal["first_visible", "largest", "explicit"] = "first_visible"
    explicit_table_ids: dict[UUID, str] = Field(default_factory=dict)
    previous_fingerprints: list[str] = Field(default_factory=list)


class BatchSourceItem(StrictModel):
    source_id: UUID
    filename: str
    relative_path: str
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    file_type: Literal["csv", "xlsx", "xlsm"]
    table_id: str | None = None
    discovered_schema: list[CanonicalField] = Field(default_factory=list)
    discovery: TableDiscovery | None = None
    row_estimate: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    state: BatchSourceState
    processing_eligible: bool
    duplicate_of: UUID | None = None


class BatchCatalog(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    items: list[BatchSourceItem]
    files_considered: int = Field(ge=0)
    files_eligible: int = Field(ge=0)
    files_duplicate: int = Field(ge=0)
    files_unchanged: int = Field(ge=0)
    files_quarantined: int = Field(ge=0)
    total_row_estimate: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class MissingRequiredPolicy(StrEnum):
    REJECT_FILE = "reject_file"
    QUARANTINE_FILE = "quarantine_file"
    BLOCK_BATCH = "block_batch"
    ALLOW_APPROVED_VALUE = "allow_approved_value"


class ExtraFieldPolicy(StrEnum):
    IGNORE = "ignore"
    INCLUDE = "include"
    BLOCK = "block"


class AlignmentCellStatus(StrEnum):
    MAPPED = "mapped"
    DEFAULTED = "defaulted"
    CONSTANT = "constant"
    MISSING_OPTIONAL = "missing_optional"
    MISSING_REQUIRED = "missing_required"
    EXTRA = "extra"
    TYPE_MISMATCH = "type_mismatch"


class SourceAlignmentConfiguration(StrictModel):
    source_id: UUID
    mapping: MappingSet
    table_id: str | None = None
    user_decisions: dict[str, Literal["accept", "reject", "manual"]] = Field(default_factory=dict)


class SchemaAlignmentPlan(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    canonical_fields: list[CanonicalField]
    sources: list[SourceAlignmentConfiguration] = Field(min_length=1)
    required_missing_policy: MissingRequiredPolicy = MissingRequiredPolicy.BLOCK_BATCH
    extra_field_policy: ExtraFieldPolicy = ExtraFieldPolicy.IGNORE
    created_by: str = "local-user"
    created_at: datetime = Field(default_factory=utc_now)


class AlignmentMatrixCell(StrictModel):
    canonical_field_id: str | None
    source_id: UUID
    source_field: str | None
    confidence: float = Field(default=0, ge=0, le=1)
    source_type: CanonicalType | None = None
    target_type: CanonicalType | None = None
    conversion: str | None = None
    status: AlignmentCellStatus
    user_decision: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SchemaAlignmentMatrix(StrictModel):
    plan_id: UUID
    plan_version: int
    cells: list[AlignmentMatrixCell]
    eligible_source_ids: list[UUID]
    rejected_source_ids: list[UUID]
    quarantined_source_ids: list[UUID]
    blocked: bool
    warnings: list[str] = Field(default_factory=list)


class DuplicateRowPolicy(StrEnum):
    KEEP_ALL = "keep_all"
    REMOVE_EXACT = "remove_exact"
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"
    REJECT = "reject"
    ROUTE_REVIEW = "route_review"


class AppendConfiguration(StrictModel):
    output_field_order: list[str] = Field(default_factory=list)
    duplicate_policy: DuplicateRowPolicy = DuplicateRowPolicy.KEEP_ALL
    duplicate_key_fields: list[str] = Field(default_factory=list)
    include_source_lineage: bool = True


class JoinType(StrEnum):
    INNER = "inner"
    LEFT = "left"
    RIGHT = "right"
    FULL = "full"
    SEMI = "semi"
    ANTI = "anti"


class NullKeyPolicy(StrEnum):
    NEVER_MATCH = "never_match"
    MATCH_NULLS = "match_nulls"
    REJECT = "reject"


class DuplicateKeyPolicy(StrEnum):
    ALLOW = "allow"
    BLOCK_MANY_TO_MANY = "block_many_to_many"
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"


class JoinConfiguration(StrictModel):
    left_source_id: UUID
    right_source_id: UUID
    join_type: JoinType
    left_keys: list[str] = Field(min_length=1)
    right_keys: list[str] = Field(min_length=1)
    key_normalisation: list[Literal["trim", "lowercase", "uppercase", "normalise_spaces"]] = Field(default_factory=list)
    null_key_policy: NullKeyPolicy = NullKeyPolicy.NEVER_MATCH
    duplicate_key_policy: DuplicateKeyPolicy = DuplicateKeyPolicy.BLOCK_MANY_TO_MANY
    approve_many_to_many: bool = False
    output_fields: list[str] = Field(default_factory=list)
    suffix: str = "_right"
    unmatched_output_policy: Literal["include", "separate", "discard"] = "separate"

    @model_validator(mode="after")
    def matching_key_count(self) -> JoinConfiguration:
        if len(self.left_keys) != len(self.right_keys):
            raise ValueError("join key lists must have equal length")
        return self


class JoinCardinality(StrEnum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class JoinDiagnostics(StrictModel):
    cardinality: JoinCardinality
    left_rows: int = Field(ge=0)
    right_rows: int = Field(ge=0)
    estimated_output_rows: int = Field(ge=0)
    actual_output_rows: int = Field(default=0, ge=0)
    expansion_ratio: float = Field(default=0, ge=0)
    null_left_keys: int = Field(default=0, ge=0)
    null_right_keys: int = Field(default=0, ge=0)
    duplicate_left_keys: int = Field(default=0, ge=0)
    duplicate_right_keys: int = Field(default=0, ge=0)
    blocked: bool = False
    warnings: list[str] = Field(default_factory=list)


class AggregationFunction(StrEnum):
    SUM = "sum"
    COUNT = "count"
    UNIQUE_COUNT = "unique_count"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    MEDIAN = "median"
    FIRST = "first"
    LAST = "last"


class AggregationMeasure(StrictModel):
    field_id: str
    function: AggregationFunction
    output_field_id: str
    null_handling: Literal["ignore", "zero", "error"] = "ignore"


class AggregationConfiguration(StrictModel):
    group_fields: list[str] = Field(min_length=1)
    measures: list[AggregationMeasure] = Field(min_length=1)
    sort_fields: list[str] = Field(default_factory=list)
    descending: bool = False
    top_n: int | None = Field(default=None, ge=1)
    percentage_of_total_fields: list[str] = Field(default_factory=list)
    rank_field: str | None = None
    rank_output_field: str = "rank"
    running_total_field: str | None = None
    running_total_output_field: str = "running_total"


class PivotConfiguration(StrictModel):
    row_fields: list[str] = Field(min_length=1)
    column_fields: list[str] = Field(min_length=1)
    value_field: str
    aggregation: AggregationFunction = AggregationFunction.SUM
    fill_value: Any | None = None
    sort_columns: bool = True
    maximum_generated_columns: int = Field(default=250, ge=1, le=10_000)


class UnpivotConfiguration(StrictModel):
    identifier_fields: list[str]
    value_fields: list[str] = Field(min_length=1)
    variable_field_name: str = "variable"
    value_field_name: str = "value"
    null_row_handling: Literal["keep", "drop"] = "drop"


class SplitMode(StrEnum):
    EXCEL_FILES = "excel_files"
    EXCEL_SHEETS = "excel_sheets"
    CSV_FILES = "csv_files"
    ZIP_PACKAGE = "zip_package"


class DateSplitPart(StrEnum):
    NONE = "none"
    YEAR = "year"
    MONTH = "month"
    QUARTER = "quarter"


class SplitConfiguration(StrictModel):
    fields: list[str] = Field(default_factory=list)
    date_part: DateSplitPart = DateSplitPart.NONE
    maximum_rows_per_file: int | None = Field(default=None, ge=1, le=1_048_575)
    condition: ExpressionNode | None = None
    minimum_group_size: int = Field(default=1, ge=1)
    mode: SplitMode = SplitMode.EXCEL_FILES
    naming_template: str = Field(default="{project}_{split_value}_{run_date}", min_length=1, max_length=240)
    project_label: str = "datapilot"
    report_type: str = "output"


class CompositionOperation(StrEnum):
    APPEND = "append"
    UNION = "union"
    JOIN = "join"
    AGGREGATE = "aggregate"
    PIVOT = "pivot"
    UNPIVOT = "unpivot"


class CompositionPlan(StrictModel):
    schema_version: Literal["2a.1"] = "2a.1"
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    project_id: UUID
    display_name: str = Field(min_length=1, max_length=120)
    source_ids: list[UUID] = Field(min_length=1, max_length=5_000)
    discovery_overrides: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)
    alignment: SchemaAlignmentPlan
    operation: CompositionOperation
    append: AppendConfiguration | None = None
    join: JoinConfiguration | None = None
    aggregation: AggregationConfiguration | None = None
    pivot: PivotConfiguration | None = None
    unpivot: UnpivotConfiguration | None = None
    split: SplitConfiguration | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def operation_configuration_present(self) -> CompositionPlan:
        required = {
            CompositionOperation.APPEND: self.append,
            CompositionOperation.UNION: self.append,
            CompositionOperation.JOIN: self.join,
            CompositionOperation.AGGREGATE: self.aggregation,
            CompositionOperation.PIVOT: self.pivot,
            CompositionOperation.UNPIVOT: self.unpivot,
        }
        if required[self.operation] is None:
            raise ValueError(f"configuration required for {self.operation}")
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("composition source IDs must be unique")
        aligned = {source.source_id for source in self.alignment.sources}
        if aligned != set(self.source_ids):
            raise ValueError("alignment sources must match composition source IDs")
        if self.join is not None and {
            self.join.left_source_id,
            self.join.right_source_id,
        } - set(self.source_ids):
            raise ValueError("join inputs must be composition sources")
        return self


class CompositionPreviewRequest(StrictModel):
    plan: CompositionPlan
    row_limit: int = Field(default=100, ge=1, le=1_000)


class CompositionRunRequest(StrictModel):
    plan: CompositionPlan
    idempotency_key: str | None = Field(default=None, max_length=120)


class CompositionJobSubmission(StrictModel):
    run: CompositionRunRequest
    retry_of: UUID | None = None


class CompositionPreview(StrictModel):
    operation: CompositionOperation
    rows: list[dict[str, Any]]
    alignment: SchemaAlignmentMatrix
    input_rows: int = Field(ge=0)
    output_rows: int = Field(ge=0)
    rejected_rows: int = Field(ge=0)
    duplicate_rows: int = Field(ge=0)
    group_count: int = Field(default=0, ge=0)
    null_impact: int = Field(default=0, ge=0)
    estimated_peak_memory_bytes: int = Field(default=0, ge=0)
    generated_columns: int = Field(default=0, ge=0)
    join_diagnostics: JoinDiagnostics | None = None
    warnings: list[str] = Field(default_factory=list)


class OutputManifestEntry(StrictModel):
    relative_path: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: int = Field(default=0, ge=0)
    split_key: str | None = None


class BatchManifest(StrictModel):
    run_id: UUID
    plan_id: UUID
    plan_version: int
    status: RunStatus
    source_items: list[BatchSourceItem]
    outputs: list[OutputManifestEntry]
    files_considered: int = Field(ge=0)
    files_accepted: int = Field(ge=0)
    files_rejected: int = Field(ge=0)
    rows_read: int = Field(ge=0)
    rows_output: int = Field(ge=0)
    rows_rejected: int = Field(ge=0)
    rows_review: int = Field(default=0, ge=0)
    rows_filtered: int = Field(default=0, ge=0)
    duplicate_rows: int = Field(ge=0)
    source_row_counts: dict[str, int] = Field(default_factory=dict)
    row_reconciliation: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
