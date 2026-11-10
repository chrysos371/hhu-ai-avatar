import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
const python = existsSync("../../envs/hhu-ai-avatar/bin/python")
  ? "../../envs/hhu-ai-avatar/bin/python"
  : "python";
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:18765",
    headless: true,
    trace: "retain-on-failure",
  },
  webServer: {
    command: python + " ../tests/helpers/serve_admin_e2e.py",
    url: "http://127.0.0.1:18765",
    reuseExistingServer: false,
    timeout: 20000,
  },
});
