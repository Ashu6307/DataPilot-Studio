import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const apiBase = "http://127.0.0.1:8001/api/v1";

test("workspace is responsive and exposes the local safety model", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Turn changing data into reliable outputs/i })).toBeVisible();
  await expect(page.getByText("Immutable source mode")).toBeVisible();
  await expect(page.getByRole("button", { name: /Source inspection/i })).toBeDisabled();
});

test("completes the guided CSV to audited export journey", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Project name").fill("E2E quality workspace");
  await page.getByRole("button", { name: "Create local project" }).click();
  await expect(page.getByRole("heading", { name: "Import a dataset." })).toBeVisible();

  const fixture = path.resolve(process.cwd(), "../../tests/fixtures/header_row_1.csv");
  await page.locator('input[type="file"]').setInputFiles(fixture);
  await expect(page.getByRole("heading", { name: "Review what DataPilot found." })).toBeVisible();
  await page.getByRole("button", { name: "Review profiles" }).click();
  await expect(page.getByRole("heading", { name: "Understand every column before changing it." })).toBeVisible();
  await page.getByRole("button", { name: "Map columns" }).click();
  await page.getByRole("button", { name: "Configure cleaning" }).click();
  await expect(page.getByRole("heading", { name: "Review schema drift before rules run." })).toBeVisible();
  await page.getByRole("button", { name: "Continue to cleaning" }).click();
  await expect(page.getByText("3 cleaning steps")).toBeVisible();
  await page.getByRole("button", { name: "Configure calculations" }).click();
  await expect(page.getByRole("heading", { name: "Build calculations as inspectable trees." })).toBeVisible();
  await page.getByRole("button", { name: "Configure validation" }).click();
  await expect(page.getByText("3 active rules")).toBeVisible();
  await page.getByRole("button", { name: "Save workflow & preview" }).click();
  await expect(page.getByRole("heading", { name: "Review row impact and exceptions." })).toBeVisible();
  await page.getByRole("button", { name: "Execute full run" }).click();
  await expect(page.getByRole("heading", { name: /Run completed/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download workbook" })).toBeVisible();
});

test("reuses a saved workflow after explicit schema-drift repair", async ({ request }) => {
  const projectResponse = await request.post(`${apiBase}/projects`, { data: { name: "Drift reuse proof" } });
  expect(projectResponse.ok()).toBeTruthy();
  const project = await projectResponse.json();
  const workflowPath = path.resolve(process.cwd(), "../../samples/profiles/generic_monthly_consolidation/workflow.json");
  const workflow = JSON.parse(fs.readFileSync(workflowPath, "utf8"));
  workflow.project_id = project.id;
  workflow.id = crypto.randomUUID();
  workflow.mapping.id = crypto.randomUUID();
  const saveResponse = await request.post(`${apiBase}/workflows`, { data: workflow });
  expect(saveResponse.ok()).toBeTruthy();
  const branchPath = path.resolve(process.cwd(), "../../samples/profiles/generic_monthly_consolidation/branch_b.csv");
  const uploadResponse = await request.post(`${apiBase}/sources`, { multipart: { project_id: project.id, file: { name: "branch_b.csv", mimeType: "text/csv", buffer: fs.readFileSync(branchPath) } } });
  const source = await uploadResponse.json();
  const discoveryResponse = await request.post(`${apiBase}/sources/${source.id}/discover`, { data: { header_search_depth: 25, preview_rows: 25 } });
  const observed = (await discoveryResponse.json()).tables[0];
  const driftResponse = await request.post(`${apiBase}/schema-drift/analyze`, { data: { expectation: { sheet_name: null, header_levels: 1, mapping: workflow.mapping }, observed, policy: { mode: "require_confirmation" } } });
  const drift = await driftResponse.json();
  expect(drift.findings.filter((item: { category: string }) => item.category === "column_renamed")).toHaveLength(3);
  const decisions = Object.entries(drift.candidates).map(([canonical_field_id, candidates]) => ({ canonical_field_id, action: "accept", selected_source_column: (candidates as Array<{ source_column: string }>)[0].source_column, reason: "Playwright-reviewed drift" }));
  const repairResponse = await request.post(`${apiBase}/mappings/repair`, { data: { project_id: project.id, workflow_id: workflow.id, mapping: workflow.mapping, decisions } });
  expect(repairResponse.ok()).toBeTruthy();
  expect((await repairResponse.json()).mapping.version).toBe(2);
});

test("composes multiple files through preview, background execution, and manifest", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Project name").fill("M2A composition proof");
  await page.getByRole("button", { name: "Create local project" }).click();
  await page.getByRole("button", { name: /Composition studio/i }).click();
  await expect(page.getByRole("heading", { name: /Compose changing datasets/i })).toBeVisible();
  const first = path.resolve(process.cwd(), "../../tests/fixtures/composition/same_schema_a.csv");
  const second = path.resolve(process.cwd(), "../../tests/fixtures/composition/renamed_columns.csv");
  await page.getByLabel(/Choose multiple Excel or CSV files/i).setInputFiles([first, second]);
  const catalog = page.locator(".composition-catalog");
  await expect(catalog.getByText("same_schema_a.csv", { exact: true })).toBeVisible();
  await expect(catalog.getByText("renamed_columns.csv", { exact: true })).toBeVisible();
  await page.getByLabel("Map employee_id for renamed_columns.csv").selectOption("emp_code");
  await page.getByLabel("Map department for renamed_columns.csv").selectOption("dept");
  await page.getByLabel("Map amount for renamed_columns.csv").selectOption("net_value");
  await page.getByRole("button", { name: /Preview composition/i }).click();
  await expect(page.getByText(/2 input → 2 output rows/i)).toBeVisible();
  await page.getByRole("button", { name: /Execute full batch/i }).click();
  await expect(page.getByText(/fingerprinted artifacts/i)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("processed-output.csv")).toBeVisible();
  await expect(page.getByText("rejected-files.json")).toBeVisible();
});

test("compares and reconciles two datasets through governed background execution", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Project name").fill("M2B reconciliation proof");
  await page.getByRole("button", { name: "Create local project" }).click();
  await page.getByRole("button", { name: /Reconciliation studio/i }).click();
  await expect(page.getByRole("heading", { name: /Reconcile changing datasets/i })).toBeVisible();
  const left = path.resolve(process.cwd(), "../../samples/profiles/old_new_report_comparison/left.csv");
  const right = path.resolve(process.cwd(), "../../samples/profiles/old_new_report_comparison/right.csv");
  const uploadPanels = page.locator(".workspace-grid .panel");
  await uploadPanels.nth(0).locator('input[type="file"]').setInputFiles(left);
  await uploadPanels.nth(1).locator('input[type="file"]').setInputFiles(right);
  await expect(page.getByRole("heading", { name: /Canonical business key/i })).toBeVisible();
  await page.getByRole("combobox", { name: "Business key", exact: true }).selectOption("record_key");
  await page.getByRole("button", { name: /Preview execution/i }).click();
  await expect(page.getByText(/candidate pairs/i).first()).toBeVisible();
  await page.getByRole("button", { name: /Execute full reconciliation/i }).click();
  await expect(page.getByText(/fingerprinted outputs/i)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("reconciliation-result.json")).toBeVisible();
  await expect(page.getByRole("link", { name: /deterministic ZIP package/i })).toBeVisible();
});
