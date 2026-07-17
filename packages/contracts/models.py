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
    header_search_depth: int = Field(default=25, ge=1, le=200)
    preview_rows: int = Field(default=25, ge=1, le=200)


class HeaderCandidate(StrictModel):
    row_number: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    labels: list[str]
    evidence: list[str]


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
    row_count_estimate: int = Field(ge=0)
    column_count: int = Field(ge=0)
    blank_leading_rows: int = Field(ge=0)
    blank_trailing_rows: int = Field(ge=0)
    repeated_header_rows: list[int] = Field(default_factory=list)
    footer_rows: list[int] = Field(default_factory=list)
    columns: list[ColumnProfile]
    preview: list[dict[str, Any]]
    confidence: float = Field(ge=0, le=1)
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


class OperationNode(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    operation_version: int = Field(default=1, ge=1)
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ValidationRule(StrictModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_-]*$", max_length=80)
    rule_type: Literal[
        "required", "data_type", "unique", "allowed_values", "min_max", "text_length", "regex"
    ]
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
    schema_version: Literal["1.0"] = "1.0"
    compatibility_version: Literal[1] = 1
    id: UUID = Field(default_factory=uuid4)
    workflow_version: int = Field(default=1, ge=1)
    project_id: UUID
    display_name: str = Field(min_length=1, max_length=120)
    source_connector: Literal["file.excel", "file.csv"]
    discovery_overrides: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)
    mapping: MappingSet
    operations: list[OperationNode] = Field(default_factory=list)
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
    rows_read: int
    rows_written: int
    rows_rejected: int
    rows_filtered: int


class RunRequest(StrictModel):
    source_id: UUID
    workflow: WorkflowConfiguration
    idempotency_key: str | None = Field(default=None, max_length=120)


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
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    operations: list[OperationMetric] = Field(default_factory=list)
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

