import { defineConfig } from "vitest/config";
export default defineConfig({
  test: { include: ["frontend/**/*.test.{ts,tsx}"], environment: "jsdom" },
});
