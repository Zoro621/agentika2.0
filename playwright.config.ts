import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/browser",
  timeout: 90000,
  expect: { timeout: 45000 },
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: process.env.CB_TEST_URL || "http://127.0.0.1:8000",
    channel: process.env.CB_BROWSER || "msedge",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 1000 } } },
    {
      name: "mobile",
      use: { ...devices["Pixel 7"], viewport: { width: 360, height: 800 } },
    },
  ],
  reporter: [["list"], ["html", { open: "never" }]],
});
