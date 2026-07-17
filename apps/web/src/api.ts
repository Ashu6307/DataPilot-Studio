import type { DiscoveryResult, PreviewResult, Project, RunRecord, SourceHandle, Workflow } from "./types";

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
  listRuns: (projectId?: string) => request<RunRecord[]>(`/runs${projectId ? `?project_id=${projectId}` : ""}`),
  artifactUrl: (runId: string, index = 0) => `${API_BASE}/artifacts/${runId}/${index}`,
};

