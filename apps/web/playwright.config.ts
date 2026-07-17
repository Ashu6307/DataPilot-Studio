import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:5173", trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    { command: "npm run dev", url: "http://127.0.0.1:5173", reuseExistingServer: true, timeout: 120_000 },
    {
      command: ".\\.venv\\Scripts\\python.exe -m uvicorn apps.api.app.main:app",
      cwd: "../..",
      url: "http://127.0.0.1:8000/health",
      reuseExistingServer: true,
      timeout: 120_000,
    },
  ],
});
