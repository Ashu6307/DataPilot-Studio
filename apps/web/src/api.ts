import type {
  BackgroundJob, BatchCatalog, BatchManifest, CompositionPlan, CompositionPreview, DiscoveryResult,
  PreviewResult, Project, RunRecord, SchemaDriftResult, SourceHandle, TableDiscovery, Workflow,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  createProject: (name: string) =>
    request<Project>("/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, locale: "en-IN", privacy_mode: "local_only" }),
    }),
  listProjects: () => request<Project[]>("/projects"),
  uploadSource: (projectId: string, file: File) => {
    const body = new FormData();
    body.append("project_id", projectId);
    body.append("file", file);
    return request<SourceHandle>("/sources", { method: "POST", body });
  },
  catalogBatch: (projectId: string, sourceIds: string[]) =>
    request<BatchCatalog>("/batches/catalog", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, source_ids: sourceIds }),
    }),
  scanFolder: (projectId: string, rootPath: string, recursive: boolean, includePatterns: string[], excludePatterns: string[]) =>
    request<BatchCatalog>("/folders/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_id: projectId, configuration: {
        root_path: rootPath, recursive, include_patterns: includePatterns, exclude_patterns: excludePatterns,
      } }),
    }),
  previewComposition: (plan: CompositionPlan) =>
    request<CompositionPreview>("/compositions/preview", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan, row_limit: 50 }),
    }),
  submitComposition: (plan: CompositionPlan) =>
    request<BackgroundJob>("/composition-jobs", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan, idempotency_key: crypto.randomUUID() }),
    }),
  getCompositionJob: (jobId: string) => request<BackgroundJob>(`/composition-jobs/${jobId}`),
  cancelCompositionJob: (jobId: string) => request<BackgroundJob>(`/composition-jobs/${jobId}/cancel`, { method: "POST" }),
  getBatchManifest: (runId: string) => request<BatchManifest>(`/batch-manifests/${runId}`),
  discover: (sourceId: string, sheetName: string | null = null, headerRow: number | null = null) =>
    request<DiscoveryResult>(`/sources/${sourceId}/discover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sheet_name: sheetName, header_row: headerRow, header_search_depth: 25, preview_rows: 25 }),
    }),
  saveWorkflow: (workflow: Workflow) =>
    request<Workflow>("/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(workflow),
    }),
  preview: (sourceId: string, workflow: Workflow) =>
    request<PreviewResult>("/runs/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: sourceId, workflow, limit: 50 }),
    }),
  run: (sourceId: string, workflow: Workflow) =>
    request<RunRecord>("/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: sourceId, workflow, idempotency_key: crypto.randomUUID() }),
    }),
  submitJob: (sourceId: string, workflow: Workflow) =>
    request<BackgroundJob>("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: sourceId, workflow, idempotency_key: crypto.randomUUID() }),
    }),
  getJob: (jobId: string) => request<BackgroundJob>(`/jobs/${jobId}`),
  cancelJob: (jobId: string) => request<BackgroundJob>(`/jobs/${jobId}/cancel`, { method: "POST" }),
  retryJob: (jobId: string) => request<BackgroundJob>(`/jobs/${jobId}/retry`, { method: "POST" }),
  getRun: (runId: string) => request<RunRecord>(`/runs/${runId}`),
  analyzeDrift: (workflow: Workflow, observed: TableDiscovery) =>
    request<SchemaDriftResult>("/schema-drift/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expectation: {
          sheet_name: workflow.discovery_overrides.sheet_name,
          table_id: observed.table_id,
          start_row: observed.start_row,
          start_column: observed.start_column,
          header_levels: observed.selected_header_rows.length || 1,
          mapping: workflow.mapping,
        },
        observed,
        policy: { mode: "require_confirmation" },
      }),
    }),
  listRuns: (projectId?: string) => request<RunRecord[]>(`/runs${projectId ? `?project_id=${projectId}` : ""}`),
  artifactUrl: (runId: string, index = 0) => `${API_BASE}/artifacts/${runId}/${index}`,
};
