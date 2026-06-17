import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL || "http://127.0.0.1:8443";
const frontendUrl = new URL(baseURL);
const frontendHost = frontendUrl.hostname || "127.0.0.1";
const frontendPort = frontendUrl.port || (frontendUrl.protocol === "https:" ? "443" : "80");
const useExternalServers = process.env.E2E_USE_EXTERNAL_SERVERS === "1";
const startServers = process.env.E2E_START_SERVERS === "1" && !useExternalServers;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: startServers
    ? [
        {
          command:
            "cd ../api && if [ -x ../../.venv/bin/python ]; then ../../.venv/bin/python run_server.py --host 127.0.0.1 --port 8009; elif command -v uv >/dev/null 2>&1; then uv run python run_server.py --host 127.0.0.1 --port 8009; else python3 run_server.py --host 127.0.0.1 --port 8009; fi",
          url: "http://127.0.0.1:8009/api/health",
          reuseExistingServer: true,
          timeout: 120_000,
        },
        {
          command: `npm run dev -- --host ${frontendHost} --port ${frontendPort}`,
          url: baseURL,
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ]
    : undefined,
});
