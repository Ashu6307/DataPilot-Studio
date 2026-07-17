import { expect, test } from "@playwright/test";
import path from "node:path";

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
  await expect(page.getByText("3 cleaning steps")).toBeVisible();
  await page.getByRole("button", { name: "Configure validation" }).click();
  await expect(page.getByText("3 active rules")).toBeVisible();
  await page.getByRole("button", { name: "Save workflow & preview" }).click();
  await expect(page.getByRole("heading", { name: "Review row impact and exceptions." })).toBeVisible();
  await page.getByRole("button", { name: "Execute full run" }).click();
  await expect(page.getByRole("heading", { name: /Run completed/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Download workbook" })).toBeVisible();
});
