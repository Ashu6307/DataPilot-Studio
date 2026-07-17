export type Severity = "information" | "warning" | "error" | "blocking";
export type CanonicalType = "text" | "integer" | "decimal" | "boolean" | "date" | "datetime";

export interface Project {
  id: string;
  name: string;
  locale: string;
  privacy_mode: "local_only";
  created_at: string;
  updated_at: string;
}

export interface SourceHandle {
  id: string;
  project_id: string;
  original_filename: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
}

export interface ColumnProfile {
  source_name: string;
  inferred_type: CanonicalType;
  null_percentage: number;
  unique_count: number;
  duplicate_count: number;
  sample_values: string[];
  semantic_roles: string[];
  is_identifier_candidate: boolean;
  is_key_candidate: boolean;
  warnings: string[];
}

export interface HeaderCandidate {
  row_number: number;
  row_numbers: number[];
  confidence: number;
  labels: string[];
  flattened_labels: string[];
  evidence: string[];
}

export interface TableDiscovery {
  table_id: string;
  sheet_name: string;
  sheet_state: "visible" | "hidden" | "veryHidden";
  candidate_region: string;
  candidate_headers: HeaderCandidate[];
  selected_header_row: number;
  selected_header_rows: number[];
  header_flattening_separator: string;
  start_row: number;
  end_row: number;
  start_column: number;
  end_column: number;
  row_count_estimate: number;
  column_count: number;
  blank_leading_rows: number;
  blank_trailing_rows: number;
  repeated_header_rows: number[];
  footer_rows: number[];
  columns: ColumnProfile[];
  preview: Record<string, unknown>[];
  confidence: number;
  decision: string;
  evidence: string[];
  alternative_candidates: string[];
  user_override: Record<string, unknown>;
  warnings: string[];
}

export interface DiscoveryResult {
  source: SourceHandle;
  tables: TableDiscovery[];
  warnings: string[];
}

export interface CanonicalField {
  id: string;
  label: string;
  data_type: CanonicalType;
  required: boolean;
  nullable: boolean;
  unique: boolean;
  aliases: string[];
}

export interface ColumnMapping {
  source_column: string | null;
  canonical_field_id: string;
  confidence: number;
  user_confirmed: boolean;
  constant_value: unknown;
  default_value: unknown;
}

export interface OperationNode {
  id: string;
  operation_id: string;
  operation_version: number;
  config: Record<string, unknown>;
  enabled: boolean;
}

export type ExpressionFunction =
  | "add" | "subtract" | "multiply" | "divide" | "concatenate" | "if_then_else";

export interface ExpressionNode {
  kind: "literal" | "field" | "call";
  value: unknown;
  value_type: CanonicalType | null;
  field_id: string | null;
  function: ExpressionFunction | null;
  args: ExpressionNode[];
}

export interface CalculatedField {
  calculation_id: string;
  version: number;
  output_canonical_field: string;
  output_type: CanonicalType;
  expression: ExpressionNode;
  null_policy: "propagate" | "coalesce" | "error";
  error_policy: "set_null" | "reject_row" | "fail_run";
  divide_by_zero_policy: "set_null" | "reject_row" | "fail_run";
  reason_code: string;
  description: string;
  lineage_enabled: boolean;
}

export interface ValidationRule {
  id: string;
  rule_type: "required" | "data_type" | "unique" | "allowed_values" | "min_max" | "text_length" | "regex";
  field_id: string;
  severity: Severity;
  reason_code: string;
  message: string;
  config: Record<string, unknown>;
}

export interface Workflow {
  schema_version: "1.0" | "1.1" | "1.2" | "1.3" | "1.4";
  compatibility_version: 1;
  id: string;
  workflow_version: number;
  project_id: string;
  display_name: string;
  source_connector: "file.excel" | "file.csv";
  discovery_overrides: { sheet_name: string | null; header_row: number | null; header_rows?: number[] | null; header_search_depth: number; preview_rows: number };
  mapping: {
    id: string;
    version: number;
    canonical_fields: CanonicalField[];
    mappings: ColumnMapping[];
    created_at: string;
    created_by: string;
  };
  operations: OperationNode[];
  calculations: CalculatedField[];
  composition_plan_id?: string | null;
  composition_plan_version?: number | null;
  reconciliation_workflow_id?: string | null;
  reconciliation_workflow_version?: number | null;
  dag_workflow_id?: string | null;
  dag_workflow_version?: number | null;
  validation_rules: ValidationRule[];
  export: { filename_prefix: string; include_summary: boolean; include_rejected_rows: boolean; include_source_metadata: boolean };
  created_at: string;
  updated_at: string;
  change_note: string;
}

export type DagNodeCategory = "source" | "discovery_mapping" | "cleaning" | "validation" |
  "calculation" | "composition" | "comparison_reconciliation" | "output" | "control" | "subflow";

export type DagArtifactType = "none" | "source_reference" | "source_collection" | "discovery_metadata" |
  "canonical_dataset" | "dataset_collection" | "validation_findings" | "comparison_result" |
  "integrity_result" | "reconciliation_result" | "review_decisions" | "evidence_package" |
  "manifest" | "control" | "any";

export interface DagPort {
  id: string;
  display_name: string;
  artifact_type: DagArtifactType;
  required: boolean;
  multiple: boolean;
}

export interface NodeCapability {
  type_id: string;
  version: number;
  display_name: string;
  category: DagNodeCategory;
  input_ports: DagPort[];
  output_ports: DagPort[];
  configuration_schema: string;
  validation_method: string;
  preview_supported: boolean;
  execution_adapter_id: string;
  cancellation_supported: boolean;
  checkpoint_supported: boolean;
  retry_classification: string;
  audit_fields: string[];
  entitlement_capability_id: string;
}

export interface DagWorkflowNode {
  id: string;
  node_type_id: string;
  node_version: number;
  display_name: string;
  category: DagNodeCategory;
  position: { x: number; y: number };
  configuration: Record<string, unknown>;
  input_ports: DagPort[];
  output_ports: DagPort[];
  retry_classification: string;
  checkpoint_policy: string;
  resource_estimate: {
    estimated_rows: number | null;
    estimated_memory_bytes: number | null;
    estimated_candidate_pairs: number | null;
    warning_seconds: number | null;
    risk: "low" | "warning" | "block" | "unknown";
  };
  entitlement_capability_id: string;
  created_at: string;
  updated_at: string;
}

export interface DagWorkflowEdge {
  id: string;
  source_node_id: string;
  source_port_id: string;
  target_node_id: string;
  target_port_id: string;
  condition: Record<string, unknown> | null;
  data_contract_reference: string;
}

export interface DagWorkflow {
  schema_version: "3a.1";
  compatibility_version: 3;
  id: string;
  version: number;
  project_id: string;
  display_name: string;
  description: string;
  lifecycle: "draft" | "published" | "archived";
  owner_reference: string;
  tags: string[];
  input_parameters: Array<Record<string, unknown>>;
  nodes: DagWorkflowNode[];
  edges: DagWorkflowEdge[];
  outputs: Array<{
    id: string;
    display_name: string;
    node_id: string;
    port_id: string;
    artifact_type: DagArtifactType;
    required: boolean;
  }>;
  multiple_start_policy: "allow" | "single";
  retry_policy: { maximum_attempts: number; retry_deterministic_failures: boolean; retry_delay_seconds: number };
  cancellation_policy: { cooperative: true; preserve_completed_checkpoints: boolean; publish_partial_outputs: false };
  resource_policy: {
    maximum_nodes: number; maximum_edges: number; maximum_subflow_depth: number;
    maximum_concurrent_ready_nodes: number; maximum_payload_bytes: number; maximum_parameter_bytes: number;
    maximum_run_history: number; checkpoint_retention_days: number;
  };
  audit_policy: {
    record_parameters: boolean; exclude_sensitive_parameters: true; record_branch_decisions: boolean;
    record_node_metrics: boolean; record_artifact_fingerprints: boolean;
  };
  change_note: string;
  created_at: string;
  updated_at: string;
}

export interface DagValidationFinding {
  severity: Severity;
  reason_code: string;
  explanation: string;
  suggested_resolution: string;
  node_id: string | null;
  edge_id: string | null;
  parameter_id: string | null;
}

export interface DagValidationResult {
  workflow_id: string;
  workflow_version: number;
  valid: boolean;
  findings: DagValidationFinding[];
  topological_order: string[];
  reachable_nodes: string[];
  validated_at: string;
}

export interface DagExecutionPlan {
  id: string;
  workflow_id: string;
  workflow_version: number;
  parameter_fingerprint: string;
  plan_fingerprint: string;
  nodes: Array<{
    node_id: string; sequence: number; dependency_node_ids: string[]; parallel_group: number;
    retry_classification: string; checkpoint_policy: string; output_consumer_count: number;
    dead_output_ports: string[]; manual_checkpoint: boolean;
  }>;
  estimated_sources: number;
  estimated_rows: number | null;
  estimated_candidate_pairs: number | null;
  estimated_outputs: number;
  resource_warnings: string[];
  manual_checkpoint_nodes: string[];
  non_retryable_nodes: string[];
  created_at: string;
}

export interface DagRunRecord {
  id: string;
  project_id: string;
  workflow_id: string;
  workflow_version: number;
  plan_id: string;
  status: "queued" | "planning" | "validating" | "running" | "waiting_for_review" |
    "cancelling" | "cancelled" | "succeeded" | "partial" | "failed" | "recovery_required";
  parameter_audit: Record<string, unknown>;
  current_node_id: string | null;
  current_parallel_group: number | null;
  progress_percent: number;
  cancel_requested: boolean;
  completed_node_ids: string[];
  skipped_node_ids: string[];
  output_manifests: string[];
  output_available: boolean;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface DagManualCheckpoint {
  id: string;
  run_id: string;
  node_id: string;
  checkpoint_type: string;
  reason: string;
  available_actions: Array<"approve" | "reject" | "edit_rerun" | "skip" | "cancel">;
  status: "waiting" | "approved" | "rejected" | "skipped" | "cancelled" | "expired";
  decision_event_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface DagWorkflowDiff {
  workflow_id: string;
  from_version: number;
  to_version: number;
  compatible: boolean;
  items: Array<{ category: string; object_id: string; before: unknown; after: unknown }>;
  created_at: string;
}

export type MatchMethod = "exact" | "normalised_exact" | "numeric_tolerance" | "date_tolerance" |
  "combined_exact_tolerance" | "fuzzy_text" | "weighted_multi_field";

export interface MatchStage {
  schema_version: "2b.1";
  id: string;
  name: string;
  priority: number;
  left_key_fields: string[];
  right_key_fields: string[];
  normalisation_pipelines?: Array<Record<string, unknown> | null>;
  method: MatchMethod;
  threshold?: string;
  numeric_tolerances?: Record<string, { mode: string; tolerance: string }>;
  date_tolerances?: Record<string, { mode: string; days: number }>;
  candidate_constraints?: Array<{ id: string; method: string; left_field: string; right_field: string; parameters?: Record<string, unknown> }>;
  fuzzy_fields?: Array<{ left_field: string; right_field: string; method: string; threshold: string }>;
  weighted_fields?: Array<{ id: string; left_field: string; right_field: string; comparison: string; weight: string; fuzzy_method?: string }>;
  tie_breaking_rule?: string;
  one_to_one?: boolean;
  duplicate_handling?: string;
  output_classification?: string;
  continue_policy?: string;
}

export interface ReconciliationWorkflow {
  schema_version: "2b.1";
  id: string;
  version: number;
  project_id: string;
  display_name: string;
  left_dataset_id: string;
  right_dataset_id: string;
  left_discovery?: Record<string, unknown>;
  right_discovery?: Record<string, unknown>;
  comparison?: Record<string, unknown>;
  stages: MatchStage[];
  comparison_fields?: Array<Record<string, unknown>>;
  budgets?: Record<string, number | string>;
  evidence_fields?: string[];
  export?: Record<string, unknown>;
}

export interface MatchResult {
  left: { dataset_id: string; record_id: string; source_row: number | null; business_key: unknown[] };
  right: { dataset_id: string; record_id: string; source_row: number | null; business_key: unknown[] };
  stage_id: string;
  match_type: MatchMethod;
  score: string;
  matched_fields: string[];
  differences: Array<Record<string, unknown>>;
  reason_code: string;
  confidence: "high" | "medium" | "low";
  review_required: boolean;
  field_scores: Array<Record<string, unknown>>;
}

export interface ReviewItem {
  id: string;
  reconciliation_run_id: string;
  left_record: Record<string, unknown>;
  right_candidates: Array<Record<string, unknown>>;
  candidates: Array<Record<string, unknown>>;
  match_stage_id: string;
  field_differences: Array<Record<string, unknown>>;
  review_reason: string;
  suggested_decision: string | null;
  status: string;
  reviewer: string | null;
  decision_timestamp: string | null;
  comment: string | null;
  audit_event_ids: string[];
}

export interface ReconciliationResult {
  run_id: string;
  workflow_id: string;
  workflow_version: number;
  status: RunRecord["status"];
  matches: MatchResult[];
  review_items: ReviewItem[];
  left_unmatched: Array<Record<string, unknown>>;
  right_unmatched: Array<Record<string, unknown>>;
  field_differences: Array<Record<string, unknown>>;
  stage_estimates: Array<{ stage_id: string; estimated_pairs: number; maximum_pairs: number; estimated_memory_bytes: number; blocked: boolean; warnings: string[] }>;
  summary: ReconciliationSummary;
  audit: string[];
  warnings: string[];
  comparison_result?: { summary: Record<string, number>; records: Array<Record<string, unknown>>; field_differences: Array<Record<string, unknown>> } | null;
  integrity_result?: { summary: Record<string, number>; findings: Array<Record<string, unknown>>; blocked: boolean } | null;
}

export interface ReconciliationSummary {
  total_left_rows: number;
  total_right_rows: number;
  matched: number;
  exact_matches: number;
  normalised_matches: number;
  tolerance_matches: number;
  fuzzy_matches: number;
  weighted_matches: number;
  review_pending: number;
  left_unmatched: number;
  right_unmatched: number;
  duplicate_candidates: number;
}

export interface ReconciliationRunRecord {
  run_id: string;
  project_id: string;
  workflow_id: string;
  workflow_version: number;
  status: RunRecord["status"];
  summary: ReconciliationSummary;
  audit: string[];
  artifacts: string[];
  created_at: string;
}

export interface ReconciliationManifest {
  run_id: string;
  workflow_id: string;
  workflow_version: number;
  status: RunRecord["status"];
  entries: Array<{ relative_path: string; media_type: string; size_bytes: number; sha256: string; row_count: number; classification: string }>;
  output_counts: Record<string, number>;
  applied_rule_ids: string[];
}

export interface Finding {
  row_identifier: string;
  field_identifier: string;
  rule_identifier: string;
  severity: Severity;
  reason_code: string;
  explanation: string;
  original_value: unknown;
}

export interface PreviewResult {
  rows: Record<string, unknown>[];
  rejected_rows: Record<string, unknown>[];
  findings: Finding[];
  operation_metrics: Array<{ node_id: string; operation_id: string; affected_rows: number; rows_in: number; rows_out: number }>;
  rows_read: number;
  rows_written: number;
  rows_rejected: number;
  rows_filtered: number;
  rows_aggregated: number;
}

export interface DriftFinding {
  category: string;
  canonical_field_id: string | null;
  expected: unknown;
  observed: unknown;
  confidence: number;
  evidence: string[];
  blocking: boolean;
}

export interface SchemaDriftResult {
  findings: DriftFinding[];
  candidates: Record<string, Array<{ source_column: string; confidence: number; method: string; evidence: string[] }>>;
  policy: { mode: "auto_accept_safe" | "warn_continue" | "require_confirmation" | "block" };
  auto_accepted: Record<string, string>;
  requires_confirmation: boolean;
  blocked: boolean;
  impact_summary: string[];
}

export interface BackgroundJob {
  id: string;
  project_id: string;
  source_id: string;
  workflow_id: string;
  workflow_version: number;
  status: RunRecord["status"];
  run_id: string | null;
  current_operation: string | null;
  rows_processed: number;
  estimated_total_rows: number | null;
  progress_percent: number | null;
  cancel_requested: boolean;
  retry_eligible: boolean;
  output_available: boolean;
  warnings: string[];
  error_code: string | null;
  error_message: string | null;
}

export interface RunRecord {
  id: string;
  project_id: string;
  workflow_id: string;
  workflow_version: number;
  status: "queued" | "running" | "cancelling" | "cancelled" | "failed" | "partial" | "succeeded" | "published";
  started_at: string;
  ended_at: string | null;
  source_filename: string;
  source_fingerprint: string;
  rows_read: number;
  rows_written: number;
  rows_rejected: number;
  rows_filtered: number;
  rows_aggregated: number;
  warnings: string[];
  errors: string[];
  artifacts: string[];
  duration_ms: number;
}

export interface BatchSourceItem {
  source_id: string;
  filename: string;
  relative_path: string;
  fingerprint: string;
  file_type: "csv" | "xlsx" | "xlsm";
  table_id: string | null;
  discovered_schema: CanonicalField[];
  row_estimate: number;
  warnings: string[];
  state: "eligible" | "duplicate" | "unchanged" | "quarantined" | "unsupported" | "failed";
  processing_eligible: boolean;
}

export interface BatchCatalog {
  id: string;
  project_id: string;
  items: BatchSourceItem[];
  files_considered: number;
  files_eligible: number;
  files_duplicate: number;
  files_unchanged: number;
  files_quarantined: number;
  total_row_estimate: number;
  warnings: string[];
}

export type CompositionOperation = "append" | "union" | "join" | "aggregate" | "pivot" | "unpivot";

export interface CompositionPlan {
  schema_version: "2a.1";
  id: string;
  version: number;
  project_id: string;
  display_name: string;
  source_ids: string[];
  discovery_overrides: { header_search_depth: number; preview_rows: number };
  alignment: {
    id: string;
    version: number;
    canonical_fields: CanonicalField[];
    sources: Array<{
      source_id: string;
      mapping: {
        id: string;
        version: number;
        canonical_fields: CanonicalField[];
        mappings: ColumnMapping[];
        created_by: string;
      };
      user_decisions: Record<string, "accept" | "reject" | "manual">;
    }>;
    required_missing_policy: "reject_file" | "quarantine_file" | "block_batch" | "allow_approved_value";
    extra_field_policy: "ignore" | "include" | "block";
  };
  operation: CompositionOperation;
  append?: { output_field_order: string[]; duplicate_policy: string; duplicate_key_fields: string[]; include_source_lineage: boolean };
  join?: Record<string, unknown>;
  aggregation?: Record<string, unknown>;
  pivot?: Record<string, unknown>;
  unpivot?: Record<string, unknown>;
  split?: Record<string, unknown>;
}

export interface CompositionPreview {
  operation: CompositionOperation;
  rows: Record<string, unknown>[];
  alignment: { blocked: boolean; cells: Array<Record<string, unknown>>; warnings: string[] };
  input_rows: number;
  output_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  group_count: number;
  null_impact: number;
  estimated_peak_memory_bytes: number;
  generated_columns: number;
  join_diagnostics: Record<string, unknown> | null;
  warnings: string[];
}

export interface BatchManifest {
  run_id: string;
  plan_id: string;
  plan_version: number;
  status: RunRecord["status"];
  outputs: Array<{ relative_path: string; media_type: string; size_bytes: number; sha256: string; rows: number; split_key: string | null }>;
  files_considered: number;
  files_accepted: number;
  files_rejected: number;
  rows_read: number;
  rows_output: number;
  rows_rejected: number;
  duplicate_rows: number;
  warnings: string[];
}
