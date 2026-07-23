import { defineConfig, devices } from "@playwright/test";

// Smoke E2E against a running server. Start the app first, e.g.:
//   uv run code-intel serve   (serves API + built UI on :8000)
// then: PLAYWRIGHT_BASE_URL=http://127.0.0.1:8000 pnpm e2e
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
