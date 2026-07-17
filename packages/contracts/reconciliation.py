"""Strict, versioned contracts for generic comparison and reconciliation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from .models import (
    CanonicalType,
    DiscoveryOverrides,
    DriftPolicy,
    RunStatus,
    SchemaExpectation,
    Severity,
    StrictModel,
    TableDiscovery,
    utc_now,
)


class KeyNullPolicy(StrEnum):
    INVALID = "invalid"
    NEVER_MATCH = "never_match"
    MATCH_NULLS = "match_nulls"


class DuplicateMatchPolicy(StrEnum):
    REPORT = "report"
    BLOCK = "block"
    KEEP_FIRST = "keep_first"
    KEEP_LAST = "keep_last"
    AMBIGUOUS = "ambiguous"


class NullEquivalencePolicy(StrEnum):
    STRICT = "strict"
    NULL_LIKE = "null_like"
    EMPTY_EQUALS_NULL = "empty_equals_null"


class ComparisonCategory(StrEnum):
    ADDED_RIGHT = "added_in_right"
    REMOVED_RIGHT = "removed_from_right"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"
    DUPLICATE_LEFT = "duplicate_key_left"
    DUPLICATE_RIGHT = "duplicate_key_right"
    INVALID_KEY = "invalid_key"
    AMBIGUOUS = "ambiguous_comparison"


class DifferenceType(StrEnum):
    VALUE_CHANGED = "value_changed"
    TYPE_CHANGED = "type_changed"
    NULL_CHANGED = "null_changed"
    NUMERIC_CHANGED = "numeric_changed"
    DATE_CHANGED = "date_changed"


class Materiality(StrEnum):
    IMMATERIAL = "immaterial"
    MATERIAL = "material"
    NOT_APPLICABLE = "not_applicable"


class NormalisationOperationId(StrEnum):
    TRIM_WHITESPACE = "text.trim_whitespace"
    COLLAPSE_SPACES = "text.collapse_spaces"
    UPPERCASE = "text.uppercase"
    LOWERCASE = "text.lowercase"
    REMOVE_PUNCTUATION = "text.remove_punctuation"
    REMOVE_PREFIXES = "text.remove_prefixes"
    REMOVE_SUFFIXES = "text.remove_suffixes"
    REPLACE_DICTIONARY = "text.replace_dictionary"
    UNICODE_NORMALISE = "text.unicode_normalise"
    NULL_LIKE = "text.null_like"
    NORMALISE_LEADING_ZEROS = "identifier.normalise_leading_zeros"
    REMOVE_SEPARATORS = "identifier.remove_separators"
    CANONICAL_DATE = "identifier.canonical_date"
    CANONICAL_NUMERIC = "identifier.canonical_numeric"


class NormalisationOperation(StrictModel):
    operation_id: NormalisationOperationId
    operation_version: Literal[1] = 1
    parameters: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class NormalisationPipeline(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    operations: list[NormalisationOperation] = Field(default_factory=list, max_length=32)
    preserve_original: Literal[True] = True


class NormalisationStepAudit(StrictModel):
    operation_id: NormalisationOperationId
    operation_version: int = Field(ge=1)
    input_value: Any | None = None
    output_value: Any | None = None
    changed: bool
    reason_code: str


class NormalisationAudit(StrictModel):
    pipeline_id: UUID
    pipeline_version: int = Field(ge=1)
    original_value: Any | None = None
    normalised_value: Any | None = None
    steps: list[NormalisationStepAudit]


class NumericToleranceMode(StrEnum):
    ABSOLUTE = "absolute_difference"
    PERCENTAGE = "percentage_difference"
    RELATIVE = "relative_difference"
    CURRENCY = "currency_amount"


class NumericTolerance(StrictModel):
    mode: NumericToleranceMode
    tolerance: Decimal = Field(ge=0)
    currency_decimal_places: int = Field(default=2, ge=0, le=8)


class DateToleranceMode(StrEnum):
    SAME_DATE = "same_date"
    CALENDAR_DAYS = "calendar_days"
    BUSINESS_DAYS = "business_days"
    MONTH = "month_only"
    PERIOD = "period"


class BusinessCalendar(StrictModel):
    weekend_days: list[int] = Field(default_factory=lambda: [5, 6])
    holidays: list[date] = Field(default_factory=list)

    @field_validator("weekend_days")
    @classmethod
    def valid_weekdays(cls, values: list[int]) -> list[int]:
        if len(values) != len(set(values)) or any(value < 0 or value > 6 for value in values):
            raise ValueError("weekend days must be unique integers from 0 to 6")
        return values


class DateTolerance(StrictModel):
    mode: DateToleranceMode
    days: int = Field(default=0, ge=0, le=3660)
    period_format: str | None = Field(default=None, max_length=40)
    calendar: BusinessCalendar | None = None

    @model_validator(mode="after")
    def calendar_required(self) -> DateTolerance:
        if self.mode == DateToleranceMode.BUSINESS_DAYS and self.calendar is None:
            raise ValueError("business-day tolerance requires a configured calendar")
        if self.mode == DateToleranceMode.PERIOD and not self.period_format:
            raise ValueError("period tolerance requires period_format")
        return self


class NumericToleranceEvidence(StrictModel):
    left_value: Decimal | None = None
    right_value: Decimal | None = None
    absolute_difference: Decimal | None = None
    percentage_difference: Decimal | None = None
    configured_tolerance: Decimal
    mode: NumericToleranceMode
    passed: bool
    reason_code: str


class DateToleranceEvidence(StrictModel):
    left_value: date | None = None
    right_value: date | None = None
    calendar_day_difference: int | None = None
    business_day_difference: int | None = None
    configured_days: int
    mode: DateToleranceMode
    passed: bool
    reason_code: str


class FieldComparisonRule(StrictModel):
    field_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    data_type: CanonicalType = CanonicalType.TEXT
    case_sensitive: bool = True
    normalise_whitespace: bool = False
    null_equivalence: NullEquivalencePolicy = NullEquivalencePolicy.STRICT
    normalisation: NormalisationPipeline | None = None
    numeric_tolerance: NumericTolerance | None = None
    date_tolerance: DateTolerance | None = None
    materiality_threshold: Decimal | None = Field(default=None, ge=0)


class RecordReference(StrictModel):
    dataset_id: UUID
    record_id: str = Field(min_length=1, max_length=240)
    source_row: int | None = Field(default=None, ge=1)
    business_key: list[Any] = Field(default_factory=list)


class FieldDifference(StrictModel):
    business_key: list[Any]
    field_id: str
    left_value: Any | None = None
    right_value: Any | None = None
    difference_type: DifferenceType
    numeric_impact: Decimal | None = None
    materiality: Materiality = Materiality.NOT_APPLICABLE
    reason_code: str


class ComparisonConfiguration(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    project_id: UUID
    left_dataset_id: UUID
    right_dataset_id: UUID
    business_key_fields: list[str] = Field(min_length=1)
    key_normalisation: dict[str, NormalisationPipeline] = Field(default_factory=dict)
    key_null_policy: KeyNullPolicy = KeyNullPolicy.INVALID
    duplicate_key_policy: DuplicateMatchPolicy = DuplicateMatchPolicy.REPORT
    comparison_rules: list[FieldComparisonRule] = Field(default_factory=list)
    compare_fields: list[str] = Field(default_factory=list)
    ignore_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fields(self) -> ComparisonConfiguration:
        keys = self.business_key_fields
        if len(keys) != len(set(keys)):
            raise ValueError("business key fields must be unique")
        if set(self.compare_fields) & set(self.ignore_fields):
            raise ValueError("fields cannot be both compared and ignored")
        rule_fields = [rule.field_id for rule in self.comparison_rules]
        if len(rule_fields) != len(set(rule_fields)):
            raise ValueError("comparison rules must target unique fields")
        return self


class ComparisonRecord(StrictModel):
    category: ComparisonCategory
    business_key: list[Any]
    left: RecordReference | None = None
    right: RecordReference | None = None
    differences: list[FieldDifference] = Field(default_factory=list)
    reason_code: str


class ComparisonSummary(StrictModel):
    total_left_rows: int = Field(ge=0)
    total_right_rows: int = Field(ge=0)
    matched_keys: int = Field(ge=0)
    added: int = Field(ge=0)
    removed: int = Field(ge=0)
    modified: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    duplicate_left_keys: int = Field(ge=0)
    duplicate_right_keys: int = Field(ge=0)
    invalid_left_keys: int = Field(ge=0)
    invalid_right_keys: int = Field(ge=0)
    ambiguous: int = Field(default=0, ge=0)


class ComparisonResult(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    configuration_id: UUID
    configuration_version: int = Field(ge=1)
    records: list[ComparisonRecord]
    field_differences: list[FieldDifference]
    summary: ComparisonSummary
    warnings: list[str] = Field(default_factory=list)


class StructureDifferenceCategory(StrEnum):
    ADDED_COLUMN = "added_column"
    REMOVED_COLUMN = "removed_column"
    RENAMED_OR_REMAPPED = "renamed_or_remapped_column"
    REORDERED_COLUMN = "reordered_column"
    DATA_TYPE_CHANGED = "data_type_changed"
    NULLABILITY_CHANGED = "nullability_changed"
    UNEXPECTED_VALUES = "new_unexpected_values"
    KEY_UNIQUENESS_CHANGED = "key_uniqueness_changed"
    HEADER_LEVEL_CHANGED = "header_level_changed"
    SELECTED_TABLE_CHANGED = "selected_table_changed"


class StructureDifference(StrictModel):
    category: StructureDifferenceCategory
    field_id: str | None = None
    left_value: Any | None = None
    right_value: Any | None = None
    severity: Severity
    compatibility_impact: Literal["none", "compatible", "review", "breaking"]
    recommended_action: str
    workflow_reuse_impact: str
    reason_code: str


class StructureComparisonResult(StrictModel):
    differences: list[StructureDifference]
    compatible: bool
    requires_review: bool
    summary: dict[str, int]


class StructureComparisonRequest(StrictModel):
    expectation: SchemaExpectation
    observed: TableDiscovery
    policy: DriftPolicy = Field(default_factory=DriftPolicy)
    expected_key_unique: bool | None = None
    observed_key_unique: bool | None = None


class ReferentialIntegrityConfiguration(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    project_id: UUID
    parent_dataset_id: UUID
    child_dataset_id: UUID
    parent_key_fields: list[str] = Field(min_length=1)
    child_reference_fields: list[str] = Field(min_length=1)
    key_normalisation: list[NormalisationPipeline | None] = Field(default_factory=list)
    null_reference_policy: Literal["allow", "report", "reject"] = "report"
    duplicate_parent_key_policy: DuplicateMatchPolicy = DuplicateMatchPolicy.REPORT
    severity: Severity = Severity.ERROR
    failure_action: Literal["continue", "partial", "block"] = "partial"

    @model_validator(mode="after")
    def matching_key_arity(self) -> ReferentialIntegrityConfiguration:
        if len(self.parent_key_fields) != len(self.child_reference_fields):
            raise ValueError("parent and child key lists must have equal length")
        if self.key_normalisation and len(self.key_normalisation) != len(self.parent_key_fields):
            raise ValueError("normalisation list must match composite key arity")
        return self


class IntegrityFinding(StrictModel):
    category: Literal[
        "valid_child_reference",
        "missing_parent_reference",
        "duplicate_parent_key",
        "null_child_reference",
        "parent_without_child",
    ]
    key: list[Any]
    parent_references: list[RecordReference] = Field(default_factory=list)
    child_references: list[RecordReference] = Field(default_factory=list)
    severity: Severity
    reason_code: str


class IntegritySummary(StrictModel):
    parent_rows: int = Field(ge=0)
    child_rows: int = Field(ge=0)
    valid_child_references: int = Field(ge=0)
    missing_parent_references: int = Field(ge=0)
    duplicate_parent_key_groups: int = Field(ge=0)
    null_child_references: int = Field(ge=0)
    parents_without_children: int = Field(ge=0)


class IntegrityResult(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    configuration_id: UUID
    configuration_version: int
    findings: list[IntegrityFinding]
    summary: IntegritySummary
    audit: list[str]
    blocked: bool


class MatchMethod(StrEnum):
    EXACT = "exact"
    NORMALISED_EXACT = "normalised_exact"
    NUMERIC_TOLERANCE = "numeric_tolerance"
    DATE_TOLERANCE = "date_tolerance"
    COMBINED = "combined_exact_tolerance"
    FUZZY_TEXT = "fuzzy_text"
    WEIGHTED = "weighted_multi_field"


class FuzzyMethod(StrEnum):
    LEVENSHTEIN = "levenshtein_similarity"
    TOKEN_SORT = "token_sort_similarity"
    TOKEN_SET = "token_set_similarity"
    NORMALISED = "normalised_string_similarity"


class BlockingMethod(StrEnum):
    EXACT = "exact"
    MONTH = "same_month"
    FIRST_CHARACTER = "same_first_character"
    AMOUNT_BUCKET = "same_amount_bucket"
    DATE_WINDOW = "same_date_window"
    CATEGORY = "same_canonical_category"
    PREFIX = "prefix_bucket"


class CandidateConstraint(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    method: BlockingMethod
    left_field: str
    right_field: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class FuzzyFieldConfiguration(StrictModel):
    left_field: str
    right_field: str
    method: FuzzyMethod
    threshold: Decimal = Field(ge=0, le=1)
    normalisation: NormalisationPipeline | None = None


class WeightedFieldConfiguration(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    left_field: str
    right_field: str
    comparison: Literal["exact", "fuzzy", "numeric_proximity", "date_proximity"]
    weight: Decimal = Field(gt=0, le=1)
    required: bool = False
    missing_value_behavior: Literal["zero", "ignore_reweight", "fail"] = "zero"
    fuzzy_method: FuzzyMethod | None = None
    numeric_tolerance: NumericTolerance | None = None
    date_tolerance: DateTolerance | None = None


class ReconciliationBudgets(StrictModel):
    maximum_candidate_pairs: int = Field(default=1_000_000, ge=1, le=100_000_000)
    maximum_duplicate_group_size: int = Field(default=10_000, ge=1, le=1_000_000)
    maximum_review_items: int = Field(default=50_000, ge=1, le=1_000_000)
    maximum_fuzzy_fields: int = Field(default=5, ge=1, le=20)
    minimum_fuzzy_threshold: Decimal = Field(default=Decimal("0.70"), ge=0, le=1)
    maximum_export_sheets: int = Field(default=30, ge=1, le=250)
    maximum_export_rows_per_sheet: int = Field(default=1_000_000, ge=1, le=1_048_575)
    maximum_execution_time_warning_seconds: int = Field(default=1800, ge=1)
    maximum_snapshot_fields: int = Field(default=20, ge=1, le=100)


def _default_reconciliation_formats() -> list[Literal["excel", "csv", "json", "zip"]]:
    return ["excel", "csv", "json", "zip"]


class ReconciliationExportConfiguration(StrictModel):
    formats: list[Literal["excel", "csv", "json", "zip"]] = Field(
        default_factory=_default_reconciliation_formats
    )
    include_outputs: list[str] = Field(default_factory=list)
    filename_prefix: str = Field(default="reconciliation_evidence", pattern=r"^[A-Za-z0-9_-]+$")


class MatchStage(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    name: str = Field(min_length=1, max_length=120)
    priority: int = Field(ge=1)
    left_key_fields: list[str] = Field(min_length=1)
    right_key_fields: list[str] = Field(min_length=1)
    normalisation_pipelines: list[NormalisationPipeline | None] = Field(default_factory=list)
    method: MatchMethod
    threshold: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    numeric_tolerances: dict[str, NumericTolerance] = Field(default_factory=dict)
    date_tolerances: dict[str, DateTolerance] = Field(default_factory=dict)
    candidate_constraints: list[CandidateConstraint] = Field(default_factory=list)
    fuzzy_fields: list[FuzzyFieldConfiguration] = Field(default_factory=list)
    weighted_fields: list[WeightedFieldConfiguration] = Field(default_factory=list)
    tie_breaking_rule: Literal["none", "highest_score", "lowest_difference", "stable_record_id"] = "none"
    one_to_one: bool = True
    duplicate_handling: DuplicateMatchPolicy = DuplicateMatchPolicy.AMBIGUOUS
    output_classification: str = Field(default="matched", max_length=80)
    continue_policy: Literal["remove_matches", "allow_reuse"] = "remove_matches"

    @model_validator(mode="after")
    def validate_stage(self) -> MatchStage:
        if len(self.left_key_fields) != len(self.right_key_fields):
            raise ValueError("left and right key lists must have equal length")
        if self.normalisation_pipelines and len(self.normalisation_pipelines) != len(self.left_key_fields):
            raise ValueError("normalisation pipelines must match key arity")
        if self.method == MatchMethod.FUZZY_TEXT and (not self.fuzzy_fields or not self.candidate_constraints):
            raise ValueError("fuzzy stages require fuzzy fields and candidate constraints")
        if self.method == MatchMethod.WEIGHTED:
            if not self.weighted_fields:
                raise ValueError("weighted stages require weighted fields")
            total = sum((item.weight for item in self.weighted_fields), Decimal(0))
            if total != Decimal("1"):
                raise ValueError("weighted field weights must total exactly 1")
        return self


class ReconciliationWorkflow(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    project_id: UUID
    display_name: str = Field(min_length=1, max_length=120)
    left_dataset_id: UUID
    right_dataset_id: UUID
    left_discovery: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)
    right_discovery: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)
    comparison: ComparisonConfiguration | None = None
    referential_integrity: ReferentialIntegrityConfiguration | None = None
    stages: list[MatchStage] = Field(min_length=1)
    comparison_fields: list[FieldComparisonRule] = Field(default_factory=list)
    budgets: ReconciliationBudgets = Field(default_factory=ReconciliationBudgets)
    export: ReconciliationExportConfiguration = Field(default_factory=ReconciliationExportConfiguration)
    evidence_fields: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_workflow(self) -> ReconciliationWorkflow:
        priorities = [stage.priority for stage in self.stages]
        ids = [stage.id for stage in self.stages]
        if len(priorities) != len(set(priorities)) or priorities != sorted(priorities):
            raise ValueError("stage priorities must be unique and ascending")
        if len(ids) != len(set(ids)):
            raise ValueError("stage IDs must be unique")
        fuzzy_count = max((len(stage.fuzzy_fields) for stage in self.stages), default=0)
        if fuzzy_count > self.budgets.maximum_fuzzy_fields:
            raise ValueError("fuzzy field count exceeds workflow budget")
        for stage in self.stages:
            if any(field.threshold < self.budgets.minimum_fuzzy_threshold for field in stage.fuzzy_fields):
                raise ValueError("fuzzy threshold is below workflow minimum")
        if self.comparison is not None and (
            self.comparison.left_dataset_id != self.left_dataset_id
            or self.comparison.right_dataset_id != self.right_dataset_id
        ):
            raise ValueError("comparison datasets must match reconciliation datasets")
        if self.referential_integrity is not None and (
            self.referential_integrity.parent_dataset_id != self.left_dataset_id
            or self.referential_integrity.child_dataset_id != self.right_dataset_id
        ):
            raise ValueError("integrity datasets must match left parent and right child datasets")
        return self


class CandidateEstimate(StrictModel):
    stage_id: str
    left_records: int = Field(ge=0)
    right_records: int = Field(ge=0)
    estimated_pairs: int = Field(ge=0)
    maximum_pairs: int = Field(ge=1)
    estimated_memory_bytes: int = Field(ge=0)
    blocked: bool
    warnings: list[str] = Field(default_factory=list)


class FieldScore(StrictModel):
    field_id: str
    score: Decimal = Field(ge=0, le=1)
    weight: Decimal = Field(ge=0, le=1)
    contribution: Decimal = Field(ge=0, le=1)
    left_value: Any | None = None
    right_value: Any | None = None
    reason_code: str


class MatchCandidate(StrictModel):
    left: RecordReference
    right: RecordReference
    stage_id: str
    method: MatchMethod
    score: Decimal = Field(ge=0, le=1)
    field_scores: list[FieldScore] = Field(default_factory=list)
    blocking_evidence: list[str] = Field(default_factory=list)
    contributing_fields: list[str] = Field(default_factory=list)
    conflicting_fields: list[str] = Field(default_factory=list)
    differences: list[FieldDifference] = Field(default_factory=list)
    reason_code: str
    tie: bool = False


class MatchResult(StrictModel):
    left: RecordReference
    right: RecordReference
    stage_id: str
    match_type: MatchMethod
    score: Decimal = Field(ge=0, le=1)
    matched_fields: list[str]
    differences: list[FieldDifference] = Field(default_factory=list)
    reason_code: str
    confidence: Literal["high", "medium", "low"]
    review_required: bool
    field_scores: list[FieldScore] = Field(default_factory=list)


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    ESCALATED = "escalated"
    SUPERSEDED = "superseded"


class ReviewDecision(StrEnum):
    APPROVE_SUGGESTED = "approve_suggested_match"
    APPROVE_ALTERNATE = "approve_alternate_candidate"
    REJECT_ALL = "reject_all_candidates"
    MARK_DUPLICATE = "mark_duplicate"
    DEFER = "defer"
    ESCALATE = "escalate"


class ReviewQueueItem(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    reconciliation_run_id: UUID
    left_record: dict[str, Any]
    right_candidates: list[dict[str, Any]]
    candidates: list[MatchCandidate]
    match_stage_id: str
    field_differences: list[FieldDifference] = Field(default_factory=list)
    review_reason: str
    suggested_decision: ReviewDecision | None = None
    status: ReviewStatus = ReviewStatus.PENDING
    reviewer: str | None = None
    decision_timestamp: datetime | None = None
    comment: str | None = Field(default=None, max_length=2_000)
    audit_event_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ReviewDecisionEvent(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    review_item_id: UUID
    decision: ReviewDecision
    selected_candidate_record_id: str | None = None
    reviewer: str = Field(min_length=1, max_length=120)
    comment: str | None = Field(default=None, max_length=2_000)
    supersedes_event_id: UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DecisionMemoryKind(StrEnum):
    APPROVED_SYNONYM = "approved_synonym"
    CANONICAL_MAPPING = "approved_canonical_mapping"
    ENTITY_ALIAS = "approved_entity_alias"
    REJECTED_ALIAS = "rejected_alias"
    REVIEW_PATTERN = "review_decision_pattern"


class DecisionMemory(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    kind: DecisionMemoryKind
    source_value: str = Field(max_length=500)
    canonical_value: str = Field(max_length=500)
    scope: Literal["project", "workflow"] = "project"
    workflow_id: UUID | None = None
    expires_at: datetime | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    active: bool = True
    created_by: str = Field(default="local-user", max_length=120)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def workflow_scope(self) -> DecisionMemory:
        if self.scope == "workflow" and self.workflow_id is None:
            raise ValueError("workflow-scoped memory requires workflow_id")
        return self


class DecisionMemoryAuditEvent(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    id: UUID = Field(default_factory=uuid4)
    memory_id: UUID
    action: Literal["created", "deactivated", "exported"]
    actor: str = Field(default="local-user", max_length=120)
    reason: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)


class ReconciliationSummary(StrictModel):
    total_left_rows: int = Field(ge=0)
    total_right_rows: int = Field(ge=0)
    matched: int = Field(ge=0)
    exact_matches: int = Field(ge=0)
    normalised_matches: int = Field(ge=0)
    tolerance_matches: int = Field(ge=0)
    fuzzy_matches: int = Field(ge=0)
    weighted_matches: int = Field(ge=0)
    review_pending: int = Field(ge=0)
    left_unmatched: int = Field(ge=0)
    right_unmatched: int = Field(ge=0)
    duplicate_candidates: int = Field(default=0, ge=0)


class ReconciliationResult(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    run_id: UUID
    workflow_id: UUID
    workflow_version: int = Field(ge=1)
    status: RunStatus
    matches: list[MatchResult]
    review_items: list[ReviewQueueItem]
    left_unmatched: list[RecordReference]
    right_unmatched: list[RecordReference]
    field_differences: list[FieldDifference]
    stage_estimates: list[CandidateEstimate]
    summary: ReconciliationSummary
    audit: list[str]
    warnings: list[str] = Field(default_factory=list)
    comparison_result: ComparisonResult | None = None
    integrity_result: IntegrityResult | None = None


class ReconciliationRunRecord(StrictModel):
    run_id: UUID
    project_id: UUID
    workflow_id: UUID
    workflow_version: int = Field(ge=1)
    status: RunStatus
    summary: ReconciliationSummary
    audit: list[str]
    artifacts: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ReconciliationRunRequest(StrictModel):
    workflow: ReconciliationWorkflow
    idempotency_key: str | None = Field(default=None, max_length=120)


class ReconciliationPreviewRequest(StrictModel):
    workflow: ReconciliationWorkflow
    row_limit: int = Field(default=100, ge=1, le=1_000)


class ReconciliationJobSubmission(StrictModel):
    run: ReconciliationRunRequest
    retry_of: UUID | None = None


class DecisionMemoryDeactivateRequest(StrictModel):
    actor: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class ReconciliationExportEntry(StrictModel):
    relative_path: str
    media_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    row_count: int = Field(ge=0)
    classification: str


class ReconciliationExportManifest(StrictModel):
    schema_version: Literal["2b.1"] = "2b.1"
    run_id: UUID
    workflow_id: UUID
    workflow_version: int = Field(ge=1)
    status: RunStatus
    source_dataset_ids: list[UUID]
    entries: list[ReconciliationExportEntry]
    output_counts: dict[str, int]
    applied_rule_ids: list[str]
    created_at: datetime = Field(default_factory=utc_now)
