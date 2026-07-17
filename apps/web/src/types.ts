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
  schema_version: "1.0" | "1.1";
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
  validation_rules: ValidationRule[];
  export: { filename_prefix: string; include_summary: boolean; include_rejected_rows: boolean; include_source_metadata: boolean };
  created_at: string;
  updated_at: string;
  change_note: string;
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
