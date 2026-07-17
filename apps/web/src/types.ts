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
  confidence: number;
  labels: string[];
  evidence: string[];
}

export interface TableDiscovery {
  table_id: string;
  sheet_name: string;
  sheet_state: "visible" | "hidden" | "veryHidden";
  candidate_region: string;
  candidate_headers: HeaderCandidate[];
  selected_header_row: number;
  row_count_estimate: number;
  column_count: number;
  blank_leading_rows: number;
  blank_trailing_rows: number;
  repeated_header_rows: number[];
  footer_rows: number[];
  columns: ColumnProfile[];
  preview: Record<string, unknown>[];
  confidence: number;
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
  schema_version: "1.0";
  compatibility_version: 1;
  id: string;
  workflow_version: number;
  project_id: string;
  display_name: string;
  source_connector: "file.excel" | "file.csv";
  discovery_overrides: { sheet_name: string | null; header_row: number | null; header_search_depth: number; preview_rows: number };
  mapping: {
    id: string;
    version: number;
    canonical_fields: CanonicalField[];
    mappings: ColumnMapping[];
    created_at: string;
    created_by: string;
  };
  operations: OperationNode[];
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
  warnings: string[];
  errors: string[];
  artifacts: string[];
  duration_ms: number;
}

