"""Versioned contracts shared by API, engine, and plugins."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Severity(StrEnum):
    INFORMATION = "information"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PARTIAL = "partial"
    SUCCEEDED = "succeeded"
    PUBLISHED = "published"


class CanonicalType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    locale: str = Field(default="en-IN", max_length=20)
    privacy_mode: Literal["local_only"] = "local_only"


class Project(ProjectCreate):
    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SourceHandle(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    original_filename: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime = Field(default_factory=utc_now)


class DiscoveryOverrides(StrictModel):
    sheet_name: str | None = None
    header_row: int | None = Field(default=None, ge=1)
    header_rows: list[int] | None = None
    table_id: str | None = None
    header_search_depth: int = Field(default=25, ge=1, le=200)
    preview_rows: int = Field(default=25, ge=1, le=200)
    profile_sample_rows: int = Field(default=10_000, ge=100, le=100_000)
    max_header_levels: int = Field(default=3, ge=1, le=3)
    header_flattening_separator: str = Field(default=".", min_length=1, max_length=5)

    @field_validator("header_rows")
    @classmethod
    def valid_header_rows(cls, rows: list[int] | None) -> list[int] | None:
        if rows is None:
            return None
        if not rows or len(rows) > 3 or any(row < 1 for row in rows):
            raise ValueError("header_rows must contain one to three positive row numbers")
        if rows != list(range(rows[0], rows[0] + len(rows))):
            raise ValueError("header_rows must be contiguous and ascending")
        return rows


class HeaderCandidate(StrictModel):
    row_number: int = Field(ge=1)
    row_numbers: list[int] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    labels: list[str]
    flattened_labels: list[str] = Field(default_factory=list)
    evidence: list[str]


class RowClassification(StrictModel):
    row_number: int = Field(ge=1)
    classification: Literal[
        "data", "repeated_header", "grand_total", "subtotal", "generated_footer", "signature", "note"
    ]
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class ColumnProfile(StrictModel):
    source_name: str
    inferred_type: CanonicalType
    null_percentage: float = Field(ge=0, le=100)
    unique_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    sample_values: list[str]
    semantic_roles: list[str] = Field(default_factory=list)
    is_identifier_candidate: bool = False
    is_key_candidate: bool = False
    warnings: list[str] = Field(default_factory=list)


class TableDiscovery(StrictModel):
    table_id: str
    sheet_name: str
    sheet_state: Literal["visible", "hidden", "veryHidden"] = "visible"
    candidate_region: str
    candidate_headers: list[HeaderCandidate]
    selected_header_row: int = Field(ge=1)
    selected_header_rows: list[int] = Field(default_factory=list)
    header_flattening_separator: str = "."
    start_row: int = Field(default=1, ge=1)
    end_row: int = Field(default=1, ge=1)
    start_column: int = Field(default=1, ge=1)
    end_column: int = Field(default=1, ge=1)
    row_count_estimate: int = Field(ge=0)
    column_count: int = Field(ge=0)
    blank_leading_rows: int = Field(ge=0)
    blank_trailing_rows: int = Field(ge=0)
    repeated_header_rows: list[int] = Field(default_factory=list)
    footer_rows: list[int] = Field(default_factory=list)
    row_classifications: list[RowClassification] = Field(default_factory=list)
    columns: list[ColumnProfile]
    preview: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
    decision: str = "candidate table"
    evidence: list[str] = Field(default_factory=list)
    alternative_candidates: list[str] = Field(default_factory=list)
    user_override: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DiscoveryResult(StrictModel):
    source: SourceHandle
    tables: list[TableDiscovery]
    warnings: list[str] = Field(default_factory=list)


class CanonicalField(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    data_type: CanonicalType = CanonicalType.TEXT
    required: bool = False
    nullable: bool = True
    unique: bool = False
    aliases: list[str] = Field(default_factory=list)


class ColumnMapping(StrictModel):
    source_column: str | None = None
    canonical_field_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    confidence: float = Field(default=1, ge=0, le=1)
    user_confirmed: bool = False
    constant_value: Any | None = None
    default_value: Any | None = None

    @model_validator(mode="after")
    def validate_source(self) -> ColumnMapping:
        if self.source_column is None and self.constant_value is None and self.default_value is None:
            raise ValueError("mapping requires a source column, constant, or default")
        return self


class MappingSet(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    canonical_fields: list[CanonicalField]
    mappings: list[ColumnMapping]
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str = "local-user"

    @model_validator(mode="after")
    def validate_mappings(self) -> MappingSet:
        field_ids = [field.id for field in self.canonical_fields]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("canonical field IDs must be unique")
        targets = [mapping.canonical_field_id for mapping in self.mappings]
        if len(targets) != len(set(targets)):
            raise ValueError("duplicate canonical mapping target")
        unknown = set(targets) - set(field_ids)
        if unknown:
            raise ValueError(f"mapping references unknown canonical fields: {sorted(unknown)}")
        return self


class DriftCategory(StrEnum):
    COLUMN_REORDERED = "column_reordered"
    COLUMN_RENAMED = "column_renamed"
    COLUMN_ADDED = "column_added"
    OPTIONAL_COLUMN_REMOVED = "optional_column_removed"
    REQUIRED_COLUMN_REMOVED = "required_column_removed"
    DATA_TYPE_CHANGED = "data_type_changed"
    NULLABILITY_CHANGED = "nullability_changed"
    DUPLICATE_COLUMN_INTRODUCED = "duplicate_column_introduced"
    NEW_UNEXPECTED_VALUES = "new_unexpected_values"
    HEADER_LEVEL_CHANGED = "header_level_changed"
    SHEET_RENAMED = "sheet_renamed"
    SELECTED_TABLE_MOVED = "selected_table_moved"
    AMBIGUOUS_MAPPING = "ambiguous_mapping"


class DriftPolicyMode(StrEnum):
    AUTO_ACCEPT_SAFE = "auto_accept_safe"
    WARN_CONTINUE = "warn_continue"
    REQUIRE_CONFIRMATION = "require_confirmation"
    BLOCK = "block"


class MappingMatchMethod(StrEnum):
    CANONICAL_ID = "canonical_id"
    SOURCE_ALIAS = "source_alias"
    NORMALISED_LABEL = "normalised_label"
    APPROVED_SYNONYM = "approved_synonym"
    TYPE_COMPATIBLE_SIMILARITY = "type_compatible_similarity"


class DriftPolicy(StrictModel):
    mode: DriftPolicyMode = DriftPolicyMode.REQUIRE_CONFIRMATION
    safe_accept_threshold: float = Field(default=0.95, ge=0, le=1)
    suggestion_threshold: float = Field(default=0.6, ge=0, le=1)
    ambiguity_delta: float = Field(default=0.08, ge=0, le=1)


class SchemaExpectation(StrictModel):
    sheet_name: str | None = None
    table_id: str | None = None
    start_row: int | None = Field(default=None, ge=1)
    start_column: int | None = Field(default=None, ge=1)
    header_levels: int = Field(default=1, ge=1, le=3)
    mapping: MappingSet
    allowed_values: dict[str, list[str]] = Field(default_factory=dict)
    approved_synonyms: dict[str, list[str]] = Field(default_factory=dict)


class MappingCandidate(StrictModel):
    source_column: str
    method: MappingMatchMethod
    confidence: float = Field(ge=0, le=1)
    expected_type: CanonicalType
    observed_type: CanonicalType
    sample_values: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class DriftFinding(StrictModel):
    category: DriftCategory
    canonical_field_id: str | None = None
    expected: Any | None = None
    observed: Any | None = None
    confidence: float = Field(default=1, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    blocking: bool = False


class MappingRepairAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    MANUAL = "manual"


class MappingRepairDecision(StrictModel):
    canonical_field_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    action: MappingRepairAction
    selected_source_column: str | None = None
    suggestion_confidence: float | None = Field(default=None, ge=0, le=1)
    decided_by: str = "local-user"
    decided_at: datetime = Field(default_factory=utc_now)
    reason: str = Field(default="User-reviewed schema drift", max_length=300)

    @model_validator(mode="after")
    def selected_source_required(self) -> MappingRepairDecision:
        if self.action in {MappingRepairAction.ACCEPT, MappingRepairAction.MANUAL} and not self.selected_source_column:
            raise ValueError("accepted/manual repair requires selected_source_column")
        return self


class MappingDecisionAudit(StrictModel):
    previous_mapping_version: int = Field(ge=1)
    repaired_mapping_version: int | None = Field(default=None, ge=1)
    decisions: list[MappingRepairDecision]
    created_at: datetime = Field(default_factory=utc_now)


class SchemaDriftResult(StrictModel):
    findings: list[DriftFinding]
    candidates: dict[str, list[MappingCandidate]]
    policy: DriftPolicy
    auto_accepted: dict[str, str] = Field(default_factory=dict)
    requires_confirmation: bool
    blocked: bool
    impact_summary: list[str] = Field(default_factory=list)


class SchemaDriftRequest(StrictModel):
    expectation: SchemaExpectation
    observed: TableDiscovery
    policy: DriftPolicy = Field(default_factory=DriftPolicy)


class MappingRepairRequest(StrictModel):
    project_id: UUID
    workflow_id: UUID
    run_id: UUID | None = None
    mapping: MappingSet
    decisions: list[MappingRepairDecision]


class MappingRepairResponse(StrictModel):
    mapping: MappingSet
    audit: MappingDecisionAudit


class OperationNode(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    operation_version: int = Field(default=1, ge=1)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ExpressionFunction(StrEnum):
    ADD = "add"
    SUBTRACT = "subtract"
    MULTIPLY = "multiply"
    DIVIDE = "divide"
    PERCENTAGE = "percentage"
    ABSOLUTE = "absolute"
    ROUND = "round"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    CONCATENATE = "concatenate"
    LENGTH = "length"
    SUBSTRING = "substring"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    CONTAINS = "contains"
    REPLACE = "replace"
    COALESCE = "coalesce"
    IF = "if"
    AND = "and"
    OR = "or"
    NOT = "not"
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    IN = "in"
    DATE_DIFFERENCE = "date_difference"
    ADD_DAYS = "add_days"
    EXTRACT_YEAR = "extract_year"
    EXTRACT_MONTH = "extract_month"
    EXTRACT_DAY = "extract_day"
    TODAY = "today"


class ExpressionNode(StrictModel):
    kind: Literal["literal", "field", "call"]
    value: Any | None = None
    value_type: CanonicalType | None = None
    field_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    function: ExpressionFunction | None = None
    args: list[ExpressionNode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> ExpressionNode:
        if self.kind == "literal" and self.value_type is None:
            raise ValueError("literal expression requires value_type")
        if self.kind == "field" and self.field_id is None:
            raise ValueError("field expression requires field_id")
        if self.kind == "call" and self.function is None:
            raise ValueError("call expression requires function")
        if self.kind != "call" and self.args:
            raise ValueError("only call expressions may contain args")
        return self


class CalculationNullPolicy(StrEnum):
    PROPAGATE = "propagate"
    ALLOW = "allow"


class CalculationErrorPolicy(StrEnum):
    SET_NULL = "set_null"
    REJECT_ROW = "reject_row"
    STOP = "stop"


class CalculatedFieldConfiguration(StrictModel):
    calculation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=100)
    version: int = Field(default=1, ge=1)
    output_canonical_field: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    output_type: CanonicalType
    expression: ExpressionNode
    null_policy: CalculationNullPolicy = CalculationNullPolicy.PROPAGATE
    error_policy: CalculationErrorPolicy = CalculationErrorPolicy.REJECT_ROW
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    description: str = Field(min_length=1, max_length=300)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CalculationPreviewRow(StrictModel):
    row_identifier: str
    before: dict[str, Any]
    calculated_value: Any | None = None
    error: str | None = None


class CalculationResult(StrictModel):
    output_field: str
    calculation_id: str
    calculation_version: int
    affected_rows: int = Field(ge=0)
    failed_rows: int = Field(ge=0)
    rejected_row_identifiers: list[str] = Field(default_factory=list)
    preview: list[CalculationPreviewRow] = Field(default_factory=list)
    lineage_fields: list[str] = Field(default_factory=list)
    reason_code: str


class ValidationRule(StrictModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]*$", max_length=80)
    rule_type: Literal["required", "data_type", "unique", "allowed_values", "min_max", "text_length", "regex"]
    field_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    severity: Severity = Severity.ERROR
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    message: str = Field(min_length=1, max_length=300)
    config: dict[str, Any] = Field(default_factory=dict)


class ExportConfiguration(StrictModel):
    filename_prefix: str = Field(default="datapilot_output", pattern=r"^[A-Za-z0-9_-]+$")
    include_summary: bool = True
    include_rejected_rows: bool = True
    include_source_metadata: bool = True


class WorkflowConfiguration(StrictModel):
    schema_version: Literal["1.0", "1.1", "1.2", "1.3"] = "1.3"
    compatibility_version: Literal[1] = 1
    id: UUID = Field(default_factory=uuid4)
    workflow_version: int = Field(default=1, ge=1)
    project_id: UUID
    display_name: str = Field(min_length=1, max_length=120)
    source_connector: Literal["file.excel", "file.csv"]
    discovery_overrides: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)
    mapping: MappingSet
    operations: list[OperationNode] = Field(default_factory=list)
    calculations: list[CalculatedFieldConfiguration] = Field(default_factory=list)
    composition_plan_id: UUID | None = None
    composition_plan_version: int | None = Field(default=None, ge=1)
    reconciliation_workflow_id: UUID | None = None
    reconciliation_workflow_version: int | None = Field(default=None, ge=1)
    validation_rules: list[ValidationRule] = Field(default_factory=list)
    export: ExportConfiguration = Field(default_factory=ExportConfiguration)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    change_note: str = Field(default="Initial version", max_length=300)

    @field_validator("operations")
    @classmethod
    def unique_operation_nodes(cls, nodes: list[OperationNode]) -> list[OperationNode]:
        ids = [node.id for node in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("operation node IDs must be unique")
        return nodes


class OperationMetric(StrictModel):
    node_id: UUID
    operation_id: str
    operation_version: int
    rows_in: int = Field(ge=0)
    rows_out: int = Field(ge=0)
    affected_rows: int = Field(ge=0)
    duration_ms: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class ValidationFinding(StrictModel):
    row_identifier: str
    field_identifier: str
    rule_identifier: str
    severity: Severity
    reason_code: str
    explanation: str
    original_value: Any | None = None


class PreviewRequest(StrictModel):
    source_id: UUID
    workflow: WorkflowConfiguration
    limit: int = Field(default=50, ge=1, le=200)


class PreviewResult(StrictModel):
    rows: list[dict[str, Any]]
    rejected_rows: list[dict[str, Any]]
    findings: list[ValidationFinding]
    operation_metrics: list[OperationMetric]
    calculation_results: list[CalculationResult] = Field(default_factory=list)
    rows_read: int
    rows_written: int
    rows_rejected: int
    rows_filtered: int
    rows_aggregated: int = 0


class RunRequest(StrictModel):
    source_id: UUID
    workflow: WorkflowConfiguration
    idempotency_key: str | None = Field(default=None, max_length=120)


class JobSubmission(StrictModel):
    run: RunRequest
    retry_of: UUID | None = None


class JobProgressEvent(StrictModel):
    job_id: UUID
    sequence: int = Field(ge=1)
    status: RunStatus
    current_operation: str | None = None
    rows_processed: int = Field(default=0, ge=0)
    estimated_total_rows: int | None = Field(default=None, ge=0)
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    message: str
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class CheckpointRecord(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    workflow_id: UUID
    workflow_version: int = Field(ge=1)
    workflow_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    completed_stage: str
    rows_processed: int = Field(default=0, ge=0)
    artifact_path: str | None = None
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    resumable: bool = False
    created_at: datetime = Field(default_factory=utc_now)


class BackgroundJobRecord(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    source_id: UUID
    workflow_id: UUID
    workflow_version: int = Field(ge=1)
    status: RunStatus = RunStatus.QUEUED
    correlation_id: UUID = Field(default_factory=uuid4)
    run_id: UUID | None = None
    current_operation: str | None = None
    rows_processed: int = Field(default=0, ge=0)
    estimated_total_rows: int | None = Field(default=None, ge=0)
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    cancel_requested: bool = False
    retry_eligible: bool = False
    retry_of: UUID | None = None
    output_available: bool = False
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RunRecord(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    workflow_id: UUID
    workflow_version: int
    status: RunStatus
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime | None = None
    source_filename: str
    source_fingerprint: str
    rows_read: int = 0
    rows_written: int = 0
    rows_rejected: int = 0
    rows_filtered: int = 0
    rows_aggregated: int = 0
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    operations: list[OperationMetric] = Field(default_factory=list)
    calculations: list[CalculationResult] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    duration_ms: int = 0


class ErrorDetail(StrictModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    severity: Literal["info", "warning", "error", "fatal"] = "error"
    retryable: bool = False
    recommended_action: str
    support_reference: UUID = Field(default_factory=uuid4)


class MigrationStepResult(StrictModel):
    version: int = Field(ge=1)
    name: str
    checksum: str
    status: Literal["applied", "already_current", "failed"]
    details: list[str] = Field(default_factory=list)


class DatabaseMigrationReport(StrictModel):
    from_version: int = Field(ge=0)
    to_version: int = Field(ge=0)
    backup_path: str | None = None
    steps: list[MigrationStepResult] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=utc_now)


class WorkflowMigrationReport(StrictModel):
    from_version: str
    to_version: str
    changed_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    backup_path: str | None = None
    migrated_at: datetime = Field(default_factory=utc_now)


class SupportBundleEntry(StrictModel):
    path: str
    category: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SupportBundlePreview(StrictModel):
    bundle_id: UUID = Field(default_factory=uuid4)
    entries: list[SupportBundleEntry]
    sanitised_payloads: dict[str, Any]
    excluded_by_default: list[str]
    screenshots_requested: list[str] = Field(default_factory=list)
    requires_user_approval: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class ResourcePolicy(StrictModel):
    preview_row_limit: int = Field(default=200, ge=1, le=10_000)
    profile_sample_row_limit: int = Field(default=10_000, ge=100, le=1_000_000)
    warning_file_size_bytes: int = Field(default=250_000_000, ge=1)
    maximum_file_size_bytes: int = Field(default=2_000_000_000, ge=1)
    maximum_estimated_cells: int = Field(default=5_000_000, ge=1)
    memory_risk_ratio: float = Field(default=0.25, gt=0, le=1)
    csv_batch_rows: int = Field(default=50_000, ge=100, le=1_000_000)


class ResourceRiskEstimate(StrictModel):
    file_size_bytes: int = Field(ge=0)
    estimated_rows: int = Field(ge=0)
    column_count: int = Field(ge=0)
    estimated_cells: int = Field(ge=0)
    estimated_peak_memory_bytes: int = Field(ge=0)
    available_memory_bytes: int = Field(ge=1)
    risk_level: Literal["low", "warning", "block"]
    warnings: list[str] = Field(default_factory=list)
    recommended_action: str
