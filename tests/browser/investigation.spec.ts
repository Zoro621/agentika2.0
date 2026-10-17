import { test, expect } from "@playwright/test";

test("source discovery, human correspondence, finding review, evidence, exports", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /Extraordinary claims/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Follow the published number/ })
    .click();
  await expect(
    page.getByRole("heading", { name: /Does this source snapshot/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /Same experiment and source version/ })
    .click();
  await expect(page.locator(".finding-meta")).toContainText(
    "verified artifact discrepancy",
  );
  await page.locator(".finding-row").first().click();
  await expect(page.getByText("A saved-result comparison.")).toBeVisible();
  await page.locator(".evidence-card").first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByText("SELECTED PASSAGE")).toBeVisible();
  await expect(
    page.getByRole("img", { name: /Original PDF page 1/ }),
  ).toBeVisible();
  await expect(page.locator(".pdf-page svg rect").first()).toBeAttached();
  await page
    .getByRole("img", { name: /Original PDF page 1/ })
    .screenshot({ path: `tmp/pdf-source-${testInfo.project.name}.png` });
  await expect(page.getByRole("link", { name: "Open original" })).toBeVisible();
  await page.getByRole("button", { name: "Close source" }).click();
  await expect(page.locator(".skip-link")).not.toBeFocused();
  await page.getByRole("button", { name: "Accept finding" }).click();
  await expect(page.locator(".review-current")).toHaveText("accepted");
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(page.locator(".skip-link")).not.toBeFocused();
  await expect(
    page.getByRole("group", { name: /Evidence graph/ }),
  ).toBeVisible();
  const width = await page.evaluate(() => ({
    viewport: innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  expect(width.document).toBeLessThanOrEqual(width.viewport);
  await page.screenshot({
    path: `tmp/observatory-${testInfo.project.name}.png`,
    fullPage: true,
  });
  await page.getByRole("button", { name: "Your review", exact: true }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "PDF report", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  expect(errors).toEqual([]);
});

test("keyboard file intake and clean control remain restrained", async ({
  page,
}) => {
  await page.goto("/");
  const zip = await page.request.get("/api/v1/samples/clean/download");
  await page.locator("input[type=file]").setInputFiles({
    name: "clean-control.zip",
    mimeType: "application/zip",
    buffer: await zip.body(),
  });
  await page.getByRole("button", { name: "Start investigation" }).click();
  await expect(page.getByText("The evidence holds so far")).toBeVisible();
  expect(await page.locator(".finding-row").count()).toBe(0);
  await page.getByRole("button", { name: "Experiments", exact: true }).click();
  // A missing runner must remain visible, rather than fabricate a successful run.
  await expect(
    page.getByRole("heading", { name: /Experiments & comparisons/ }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Your review", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Evidence ZIP", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("reduced motion and unavailable WebGL retain a complete intake", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.getContext = (() =>
      null) as typeof HTMLCanvasElement.prototype.getContext;
  });
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Browse files" }),
  ).toBeVisible();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Browse files" }).focus();
  await page.keyboard.press("Enter");
  await (await chooser).setFiles([]);
  await page.getByRole("button", { name: "Investigation settings" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByLabel("Analysis provider").selectOption("deterministic");
  await page.getByRole("button", { name: "Close settings" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("large inventories stay virtualized and clusters expose all stored members", async ({
  page,
}) => {
  const artifacts = Array.from({ length: 2000 }, (_, i) => ({
    id: `source-${i}`,
    path: `src/group${i % 30}/file${i}.py`,
    kind: "code",
    size: 500,
    sha256: "a".repeat(64),
  }));
  const graph = {
    nodes: artifacts.map((a) => ({
      id: a.id,
      type: "code",
      label: a.path,
      artifact_id: a.id,
      path: a.path,
    })),
    edges: [],
  };
  await page.route("**/api/v1/cases/large-ui", (route) =>
    route.fulfill({
      json: {
        id: "large-ui",
        title: "Large inventory UI acceptance",
        status: "partially_complete",
        provider: "deterministic",
        revision: 0,
        created_at: new Date().toISOString(),
        sources: [],
        decisions: [],
        artifacts,
        jobs: [],
        result: {
          claims: [],
          findings: [],
          checks: [],
          questions: [],
          executions: [],
          warnings: [],
          coverage: { files_discovered: 2000, files_inspected: 100 },
          graph,
        },
      },
    }),
  );
  await page.route("**/api/v1/cases/large-ui/events**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: ": idle\n\n",
    }),
  );
  await page.goto("/?case=large-ui");
  await expect(
    page.getByRole("heading", { name: "Large inventory UI acceptance" }),
  ).toBeVisible();
  if ((await page.viewportSize())!.width < 800)
    await page.getByRole("button", { name: "Open source explorer" }).click();
  const list = page.getByRole("list", { name: "Source files" });
  await expect(list).toBeVisible();
  expect(await list.getByRole("listitem").count()).toBeLessThan(25);
  await page
    .getByRole("textbox", { name: "Filter source files" })
    .fill("file1999.py");
  await expect(list.getByRole("listitem")).toHaveCount(1);
  if ((await page.viewportSize())!.width < 800)
    await page.getByRole("button", { name: "Close source explorer" }).click();
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await expect(page.locator(".cluster-caption")).toContainText("2000 nodes");
  await page.locator(".graph-node").first().click();
  await expect(
    page.getByRole("region", { name: "Cluster members" }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "Filter cluster members" })
    .fill("file1999.py");
  await expect(
    page
      .getByRole("list", { name: "Stored cluster members" })
      .getByRole("listitem"),
  ).toHaveCount(1);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("recorded real measurements render with a common metric and original/corrected labels", async ({
  page,
}) => {
  const { readFile } = await import("node:fs/promises");
  const recorded = JSON.parse(
    await readFile("tests/fixtures/measured-case.json", "utf8"),
  );
  await page.route("**/api/v1/cases/measured-ui", (route) =>
    route.fulfill({ json: { ...recorded, id: "measured-ui" } }),
  );
  await page.route("**/api/v1/cases/measured-ui/events**", (route) =>
    route.fulfill({ contentType: "text/event-stream", body: ": idle\n\n" }),
  );
  await page.goto("/?case=measured-ui");
  await page.getByRole("button", { name: "Experiments", exact: true }).click();
  await expect(
    page.getByRole("img", {
      name: /baseline, accuracy: 1.0000; grouped, accuracy: 0.5000/i,
    }),
  ).toBeVisible();
  await expect(page.locator(".run-card").first()).toContainText(
    "original execution",
  );
  await expect(page.locator(".run-card").nth(1)).toContainText(
    "corrected protocol",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
