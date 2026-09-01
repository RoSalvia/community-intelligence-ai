import { defineConfig } from "@playwright/test"

const localChrome = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: "list",
  use: {
    baseURL: process.env.COMMUNITY_INTELLIGENCE_BASE_URL ?? "http://127.0.0.1:8765",
    browserName: "chromium",
    launchOptions: localChrome ? { executablePath: localChrome } : undefined,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
})
