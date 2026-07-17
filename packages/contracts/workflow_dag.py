"""Strict Milestone 3A contracts for typed visual workflow DAGs."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .models import DiscoveryOverrides, ExpressionNode, Severity, StrictModel, ValidationRule, utc_now


class NodeCategory(StrEnum):
    SOURCE = "source"
    DISCOVERY = "discovery_mapping"
    CLEANING = "cleaning"
    VALIDATION = "validation"
    CALCULATION = "calculation"
    COMPOSITION = "composition"
    RECONCILIATION = "comparison_reconciliation"
    OUTPUT = "output"
    CONTROL = "control"
    SUBFLOW = "subflow"


class ArtifactType(StrEnum):
    NONE = "none"
    SOURCE_REFERENCE = "source_reference"
    SOURCE_COLLECTION = "source_collection"
    DISCOVERY = "discovery_metadata"
    CANONICAL_DATASET = "canonical_dataset"
    DATASET_COLLECTION = "dataset_collection"
    VALIDATION_FINDINGS = "validation_findings"
    COMPARISON_RESULT = "comparison_result"
    INTEGRITY_RESULT = "integrity_result"
    RECONCILIATION_RESULT = "reconciliation_result"
    REVIEW_DECISIONS = "review_decisions"
    EVIDENCE_PACKAGE = "evidence_package"
    MANIFEST = "manifest"
    BOOLEAN = "boolean"
    CONTROL = "control"
    ANY = "any"


class RetryClassification(StrEnum):
    DETERMINISTIC = "deterministic_retry"
    CHECKPOINT_ONLY = "checkpoint_only"
    MANUAL = "manual_review_required"
    NEVER = "never_retry"


class CheckpointPolicy(StrEnum):
    NONE = "none"
    AFTER_SUCCESS = "after_success"
    BEFORE_AND_AFTER = "before_and_after"
    MANUAL = "manual_checkpoint"


class WorkflowLifecycle(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DagRunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    VALIDATING = "validating"
    RUNNING = "running"
    WAITING_FOR_REVIEW = "waiting_for_review"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    RECOVERY_REQUIRED = "recovery_required"


class NodeRunStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    RECOVERED = "recovered"


class ParameterType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    FILE_REFERENCE = "file_path_reference"
    FOLDER_REFERENCE = "folder_path_reference"
    CHOICE = "choice"
    MULTI_CHOICE = "multi_choice"
    CANONICAL_FIELD = "canonical_field_selection"
    CREDENTIAL_REFERENCE = "credential_reference"


class RuntimeOverridePolicy(StrEnum):
    ALLOW = "allow"
    REQUIRE = "require"
    FORBID = "forbid"


class DagLimits(StrictModel):
    maximum_nodes: int = Field(default=250, ge=1, le=5_000)
    maximum_edges: int = Field(default=1_000, ge=0, le=20_000)
    maximum_subflow_depth: int = Field(default=5, ge=0, le=20)
    maximum_concurrent_ready_nodes: int = Field(default=4, ge=1, le=64)
    maximum_payload_bytes: int = Field(default=2_000_000, ge=1_024, le=50_000_000)
    maximum_parameter_bytes: int = Field(default=100_000, ge=256, le=5_000_000)
    maximum_run_history: int = Field(default=1_000, ge=1, le=100_000)
    checkpoint_retention_days: int = Field(default=30, ge=1, le=3_650)


class DagPosition(StrictModel):
    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)


class EmptyNodeConfiguration(StrictModel):
    pass


class SourceNodeConfiguration(StrictModel):
    source_id: UUID


class DiscoveryNodeConfiguration(StrictModel):
    overrides: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)


class SavedDatasetReference(StrictModel):
    source_id: UUID
    overrides: DiscoveryOverrides = Field(default_factory=DiscoveryOverrides)


class ValidationNodeConfiguration(StrictModel):
    rules: list[ValidationRule] = Field(default_factory=list)


class ManualCheckpointNodeConfiguration(StrictModel):
    checkpoint_type: Literal[
        "mapping_approval",
        "schema_drift_approval",
        "many_to_many_join_approval",
        "reconciliation_review",
        "quality_threshold_approval",
        "output_publication_approval",
    ] = "output_publication_approval"
    reason: str = Field(default="Manual review is required.", min_length=1, max_length=1_000)


class SubflowInstanceConfiguration(StrictModel):
    subflow_id: UUID
    subflow_version: int = Field(ge=1)
    input_bindings: dict[str, str] = Field(default_factory=dict)
    output_bindings: dict[str, str] = Field(default_factory=dict)


class ManifestConfiguration(StrictModel):
    filename_prefix: str = Field(default="datapilot_manifest", pattern=r"^[A-Za-z0-9_-]+$")


class EvidencePackageConfiguration(StrictModel):
    filename_prefix: str = Field(default="datapilot_evidence", pattern=r"^[A-Za-z0-9_-]+$")
    include_manifest: Literal[True] = True


class MergePolicy(StrictModel):
    strategy: Literal["first_available", "require_all"] = "first_available"


class StopConfiguration(StrictModel):
    reason: str = Field(default="Workflow stopped by configured policy.", min_length=1, max_length=500)


class FailConfiguration(StrictModel):
    reason_code: str = Field(default="DAG_CONFIGURED_FAILURE", pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(default="Workflow failed by configured policy.", min_length=1, max_length=500)


class DagPort(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=100)
    display_name: str = Field(min_length=1, max_length=120)
    artifact_type: ArtifactType
    required: bool = True
    multiple: bool = False


class NodeResourceEstimate(StrictModel):
    estimated_rows: int | None = Field(default=None, ge=0)
    estimated_memory_bytes: int | None = Field(default=None, ge=0)
    estimated_candidate_pairs: int | None = Field(default=None, ge=0)
    warning_seconds: int | None = Field(default=None, ge=0)
    risk: Literal["low", "warning", "block", "unknown"] = "unknown"


class DagNode(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=100)
    node_type_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=160)
    node_version: int = Field(default=1, ge=1)
    display_name: str = Field(min_length=1, max_length=160)
    category: NodeCategory
    position: DagPosition
    configuration: dict[str, Any] = Field(default_factory=dict)
    input_ports: list[DagPort] = Field(default_factory=list, max_length=32)
    output_ports: list[DagPort] = Field(default_factory=list, max_length=32)
    retry_classification: RetryClassification = RetryClassification.DETERMINISTIC
    checkpoint_policy: CheckpointPolicy = CheckpointPolicy.AFTER_SUCCESS
    resource_estimate: NodeResourceEstimate = Field(default_factory=NodeResourceEstimate)
    entitlement_capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=160)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DagEdge(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=120)
    source_node_id: str
    source_port_id: str
    target_node_id: str
    target_port_id: str
    condition: ExpressionNode | None = None
    data_contract_reference: str = Field(min_length=1, max_length=200)


class ParameterValidation(StrictModel):
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    minimum_length: int | None = Field(default=None, ge=0, le=100_000)
    maximum_length: int | None = Field(default=None, ge=0, le=100_000)
    pattern: str | None = Field(default=None, max_length=500)


class RuntimeParameterDefinition(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=100)
    label: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    data_type: ParameterType
    required: bool = False
    default_value: Any | None = None
    allowed_values: list[Any] = Field(default_factory=list, max_length=1_000)
    validation: ParameterValidation = Field(default_factory=ParameterValidation)
    secret: bool = False
    override_policy: RuntimeOverridePolicy = RuntimeOverridePolicy.ALLOW

    @model_validator(mode="after")
    def secret_reference_only(self) -> RuntimeParameterDefinition:
        if self.secret and self.data_type != ParameterType.CREDENTIAL_REFERENCE:
            raise ValueError("secret parameters must use credential_reference type")
        if self.secret and self.default_value not in (None, "credential_reference"):
            raise ValueError("secret parameter defaults may contain only a credential reference placeholder")
        return self


class DagOutputDefinition(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=100)
    display_name: str = Field(min_length=1, max_length=160)
    node_id: str
    port_id: str
    artifact_type: ArtifactType
    required: bool = True


class WorkflowRetryPolicy(StrictModel):
    maximum_attempts: int = Field(default=1, ge=1, le=10)
    retry_deterministic_failures: bool = True
    retry_delay_seconds: int = Field(default=0, ge=0, le=3_600)


class WorkflowCancellationPolicy(StrictModel):
    cooperative: Literal[True] = True
    preserve_completed_checkpoints: bool = True
    publish_partial_outputs: Literal[False] = False


class WorkflowAuditPolicy(StrictModel):
    record_parameters: bool = True
    exclude_sensitive_parameters: Literal[True] = True
    record_branch_decisions: bool = True
    record_node_metrics: bool = True
    record_artifact_fingerprints: bool = True


class DagWorkflow(StrictModel):
    schema_version: Literal["3a.1"] = "3a.1"
    compatibility_version: Literal[3] = 3
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    project_id: UUID
    display_name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2_000)
    lifecycle: WorkflowLifecycle = WorkflowLifecycle.DRAFT
    owner_reference: str = Field(default="local-user", min_length=1, max_length=160)
    tags: list[str] = Field(default_factory=list, max_length=50)
    input_parameters: list[RuntimeParameterDefinition] = Field(default_factory=list, max_length=200)
    nodes: list[DagNode] = Field(default_factory=list)
    edges: list[DagEdge] = Field(default_factory=list)
    outputs: list[DagOutputDefinition] = Field(default_factory=list, max_length=100)
    multiple_start_policy: Literal["allow", "single"] = "allow"
    retry_policy: WorkflowRetryPolicy = Field(default_factory=WorkflowRetryPolicy)
    cancellation_policy: WorkflowCancellationPolicy = Field(default_factory=WorkflowCancellationPolicy)
    resource_policy: DagLimits = Field(default_factory=DagLimits)
    audit_policy: WorkflowAuditPolicy = Field(default_factory=WorkflowAuditPolicy)
    change_note: str = Field(default="Initial DAG version", max_length=500)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class NodeCapability(StrictModel):
    type_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$", max_length=160)
    version: int = Field(default=1, ge=1)
    display_name: str
    category: NodeCategory
    input_ports: list[DagPort]
    output_ports: list[DagPort]
    configuration_schema: str
    validation_method: str
    preview_supported: bool
    execution_adapter_id: str
    cancellation_supported: bool
    checkpoint_supported: bool
    retry_classification: RetryClassification
    audit_fields: list[str]
    entitlement_capability_id: str


class DagValidationFinding(StrictModel):
    severity: Severity
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=120)
    explanation: str = Field(min_length=1, max_length=1_000)
    suggested_resolution: str = Field(min_length=1, max_length=1_000)
    node_id: str | None = None
    edge_id: str | None = None
    parameter_id: str | None = None


class DagValidationResult(StrictModel):
    workflow_id: UUID
    workflow_version: int
    valid: bool
    findings: list[DagValidationFinding]
    topological_order: list[str] = Field(default_factory=list)
    reachable_nodes: list[str] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=utc_now)


class RuntimeParameterValue(StrictModel):
    parameter_id: str
    value: Any


class ArtifactReference(StrictModel):
    artifact_id: UUID = Field(default_factory=uuid4)
    artifact_type: ArtifactType
    producer_node_id: str
    path_reference: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    row_count: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannedNode(StrictModel):
    node_id: str
    sequence: int = Field(ge=1)
    dependency_node_ids: list[str]
    parallel_group: int = Field(ge=1)
    retry_classification: RetryClassification
    checkpoint_policy: CheckpointPolicy
    resource_estimate: NodeResourceEstimate
    output_consumer_count: int = Field(ge=0)
    dead_output_ports: list[str] = Field(default_factory=list)
    manual_checkpoint: bool = False


class ExecutionPlan(StrictModel):
    schema_version: Literal["3a.1"] = "3a.1"
    id: UUID = Field(default_factory=uuid4)
    workflow_id: UUID
    workflow_version: int
    parameter_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    nodes: list[PlannedNode]
    estimated_sources: int = Field(ge=0)
    estimated_rows: int | None = Field(default=None, ge=0)
    estimated_candidate_pairs: int | None = Field(default=None, ge=0)
    estimated_outputs: int = Field(ge=0)
    resource_warnings: list[str] = Field(default_factory=list)
    manual_checkpoint_nodes: list[str] = Field(default_factory=list)
    non_retryable_nodes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class DagRunRequest(StrictModel):
    workflow: DagWorkflow
    parameters: list[RuntimeParameterValue] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=160)


class DagJobSubmission(StrictModel):
    request: DagRunRequest
    retry_of: UUID | None = None
    recovery_of: UUID | None = None


class NodeRunRecord(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    node_id: str
    node_type_id: str
    status: NodeRunStatus = NodeRunStatus.PENDING
    attempt: int = Field(default=1, ge=1)
    input_artifact_ids: list[UUID] = Field(default_factory=list)
    output_artifacts: list[ArtifactReference] = Field(default_factory=list)
    progress_percent: float = Field(default=0, ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class DagRunRecord(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    workflow_id: UUID
    workflow_version: int
    plan_id: UUID
    status: DagRunStatus = DagRunStatus.QUEUED
    parameter_audit: dict[str, Any] = Field(default_factory=dict)
    current_node_id: str | None = None
    current_parallel_group: int | None = Field(default=None, ge=1)
    progress_percent: float = Field(default=0, ge=0, le=100)
    cancel_requested: bool = False
    completed_node_ids: list[str] = Field(default_factory=list)
    skipped_node_ids: list[str] = Field(default_factory=list)
    output_manifests: list[UUID] = Field(default_factory=list)
    retry_of: UUID | None = None
    recovery_of: UUID | None = None
    output_available: bool = False
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ManualCheckpointType(StrEnum):
    MAPPING_APPROVAL = "mapping_approval"
    SCHEMA_DRIFT_APPROVAL = "schema_drift_approval"
    JOIN_CARDINALITY_APPROVAL = "many_to_many_join_approval"
    RECONCILIATION_REVIEW = "reconciliation_review"
    QUALITY_THRESHOLD = "quality_threshold_approval"
    OUTPUT_PUBLICATION = "output_publication_approval"


class ManualCheckpointStatus(StrEnum):
    WAITING = "waiting"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ManualCheckpoint(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    node_id: str
    checkpoint_type: ManualCheckpointType
    reason: str = Field(min_length=1, max_length=1_000)
    required_role_placeholder: str = Field(default="workflow_reviewer", max_length=120)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    available_actions: list[Literal["approve", "reject", "edit_rerun", "skip", "cancel"]]
    status: ManualCheckpointStatus = ManualCheckpointStatus.WAITING
    expiry_at: datetime | None = None
    decision_event_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ManualCheckpointDecision(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    checkpoint_id: UUID
    action: Literal["approve", "reject", "edit_rerun", "skip", "cancel"]
    actor: str = Field(min_length=1, max_length=160)
    comment: str | None = Field(default=None, max_length=2_000)
    supersedes_event_id: UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)


class SubflowDefinition(StrictModel):
    schema_version: Literal["3a.1"] = "3a.1"
    id: UUID = Field(default_factory=uuid4)
    version: int = Field(default=1, ge=1)
    project_id: UUID
    display_name: str = Field(min_length=1, max_length=160)
    compatibility_version: Literal[3] = 3
    public_input_ports: list[DagPort]
    public_output_ports: list[DagPort]
    runtime_parameters: list[RuntimeParameterDefinition] = Field(default_factory=list)
    nodes: list[DagNode]
    edges: list[DagEdge]
    dependencies: list[tuple[UUID, int]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowDiffItem(StrictModel):
    category: Literal[
        "node_added",
        "node_removed",
        "node_changed",
        "edge_added",
        "edge_removed",
        "parameter_changed",
        "subflow_version_changed",
        "output_changed",
        "resource_policy_changed",
    ]
    object_id: str
    before: Any | None = None
    after: Any | None = None


class WorkflowDiff(StrictModel):
    workflow_id: UUID
    from_version: int
    to_version: int
    compatible: bool
    items: list[WorkflowDiffItem]
    created_at: datetime = Field(default_factory=utc_now)


class EvidencePackageVersion(StrictModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    workflow_id: UUID
    workflow_version: int
    package_version: int = Field(ge=1)
    review_decision_version: int = Field(ge=0)
    previous_package_id: UUID | None = None
    manifest_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    affected_output_node_ids: list[str]
    reused_checkpoint_node_ids: list[str]
    regenerated_by: str = Field(min_length=1, max_length=160)
    created_at: datetime = Field(default_factory=utc_now)


class EvidenceRegenerationRequest(StrictModel):
    run_id: UUID
    actor: str = Field(min_length=1, max_length=160)


class WorkflowVersionRequest(StrictModel):
    workflow: DagWorkflow
    change_note: str = Field(min_length=1, max_length=500)


class WorkflowCloneRequest(StrictModel):
    display_name: str = Field(min_length=1, max_length=160)
    owner_reference: str = Field(default="local-user", max_length=160)


class WorkflowPlanRequest(StrictModel):
    workflow: DagWorkflow
    parameters: list[RuntimeParameterValue] = Field(default_factory=list)


class WorkflowDiffRequest(StrictModel):
    before: DagWorkflow
    after: DagWorkflow


class WorkflowRestoreRequest(StrictModel):
    source_version: int = Field(ge=1)
    change_note: str = Field(min_length=1, max_length=500)


RuntimeValue = str | int | Decimal | bool | date | datetime | list[str] | None
