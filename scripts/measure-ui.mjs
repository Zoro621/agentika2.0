import { chromium } from "@playwright/test";
import { writeFile, mkdir } from "node:fs/promises";

const browser = await chromium.launch({
  channel: process.env.CB_BROWSER || "msedge",
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 360, height: 800 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
});
const page = await context.newPage();
const cdp = await context.newCDPSession(page);
await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
await cdp.send("Network.enable");
await cdp.send("Network.emulateNetworkConditions", {
  offline: false,
  latency: 100,
  downloadThroughput: 4_000_000 / 8,
  uploadThroughput: 1_000_000 / 8,
});
await page.addInitScript(() => {
  window.__cbMetrics = { lcp: 0, cls: 0, interactions: [] };
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries())
      window.__cbMetrics.lcp = entry.startTime;
  }).observe({ type: "largest-contentful-paint", buffered: true });
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries())
      if (!entry.hadRecentInput) window.__cbMetrics.cls += entry.value;
  }).observe({ type: "layout-shift", buffered: true });
  new PerformanceObserver((list) => {
    for (const entry of list.getEntries())
      if (entry.interactionId)
        window.__cbMetrics.interactions.push({
          name: entry.name,
          duration: entry.duration,
          interaction: entry.interactionId,
        });
  }).observe({ type: "event", buffered: true, durationThreshold: 16 });
});
const requests = [];
page.on("request", (r) => {
  if (r.resourceType() === "script") requests.push(r.url().split("/").at(-1));
});
const target = process.env.CB_TEST_URL || "http://127.0.0.1:8000";
await page.goto(target);
await page.getByRole("heading", { name: /Extraordinary claims/ }).waitFor();
await page.waitForTimeout(3500);
await page.getByRole("button", { name: "Investigation settings" }).click();
await page.getByLabel("Analysis provider").selectOption("deterministic");
await page.getByRole("button", { name: "Close settings" }).click();
await page.waitForTimeout(500);
const metrics = await page.evaluate(() => window.__cbMetrics);
const result = {
  at: new Date().toISOString(),
  profile: {
    viewport: "360x800",
    deviceScaleFactor: 2,
    cpuSlowdown: 4,
    network: "4 Mbps down / 1 Mbps up / 100 ms latency",
    browser: `${process.env.CB_BROWSER || "msedge"}, headless`,
    origin: `${new URL(target).origin}; production assets; cold browser context`,
  },
  metrics: {
    lcpMs: metrics.lcp,
    cls: metrics.cls,
    observedMaxInteractionMs: Math.max(
      0,
      ...metrics.interactions.map((e) => e.duration),
    ),
  },
  scriptRequests: requests,
  limits:
    "One lab page visit with three settings interactions. Not deployed-field INP or a Lighthouse score. Rerun on the public URL for release acceptance.",
};
await mkdir("tmp/performance", { recursive: true });
await writeFile("tmp/performance/ui.json", JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
await browser.close();
