import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5174", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "npm run dev -- --port 5174",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      timeout: 120_000,
      env: { VITE_API_BASE_URL: "http://127.0.0.1:8001/api/v1" },
    },
    {
      command: ".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.app.main:app --port 8001",
      cwd: "../..",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      timeout: 120_000,
      env: { DATAPILOT_ALLOWED_ORIGINS: "http://127.0.0.1:5174" },
    },
  ],
});
