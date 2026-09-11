import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.TIZA_TEST_URL || "http://127.0.0.1:5173" },
  webServer: process.env.TIZA_TEST_URL ? undefined : { command: "pnpm dev --host 127.0.0.1", url: "http://127.0.0.1:5173", reuseExistingServer: true },
});
