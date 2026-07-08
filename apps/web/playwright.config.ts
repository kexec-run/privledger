import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "../..");
const apiPort = Number(process.env.PRIVLEDGER_E2E_API_PORT ?? "4578");
const webPort = Number(process.env.PRIVLEDGER_E2E_WEB_PORT ?? "5174");
const apiBaseUrl = `http://127.0.0.1:${apiPort}`;
const webBaseUrl = `http://127.0.0.1:${webPort}`;
const useRealRecorder = process.env.PRIVLEDGER_E2E_REAL_RECORDER === "1";
const fakeRecorder = path.join(here, "e2e", "fixtures", "fake-recorder.mjs");

const apiCommand = [
  `PRIVLEDGER_API_PORT=${apiPort}`,
  `PRIVLEDGER_ROOT=${repoRoot}`,
  useRealRecorder ? "" : `PRIVLEDGER_RECORD_COMMAND="${process.execPath} ${fakeRecorder}"`,
  "npm run dev",
].filter(Boolean).join(" ");

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: {
    timeout: 10_000,
  },
  reporter: "list",
  use: {
    baseURL: webBaseUrl,
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: apiCommand,
      cwd: path.join(repoRoot, "apps", "api"),
      url: `${apiBaseUrl}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `PRIVLEDGER_WEB_PORT=${webPort} PRIVLEDGER_API_URL=${apiBaseUrl} npm run dev`,
      cwd: here,
      url: webBaseUrl,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
