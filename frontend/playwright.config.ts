import { defineConfig } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
const assets = process.env.HHU_AVATAR_DATA_ROOT
  ?? execFileSync("python3", ["-B", resolve(__dirname, "../scripts/project_paths.py")], { encoding: "utf8" }).trim();
export default defineConfig({
  testDir: "./e2e",
  outputDir: resolve(assets, "frontend/test-results"),
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:18765",
    headless: true,
    channel: "chromium",
    launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
    trace: "retain-on-failure",
  },
  webServer: {
    command: "../scripts/project-python ../tests/helpers/serve_admin_e2e.py",
    url: "http://127.0.0.1:18765",
    reuseExistingServer: false,
    timeout: 20000,
  },
});
