import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const NAVY = "rgb(12, 74, 110)"; // #0C4A6E — frozen values must render in this colour

// Screenshot evidence lands in docs/img/console (repo root). Capture runs only with CAPTURE=1,
// so the CI gate (npm test) never writes files; screenshots are committed once, on demand.
const CAPTURE = !!process.env.CAPTURE;
const SHOT_DIR = path.resolve(__dirname, "../../../docs/img/console");

test("search → detail → review (mocked) → explain, with the visual law intact", async ({ page }) => {
  // 1. Master list, populated from the (mock) serving API.
  await page.goto("/search");
  await expect(page.getByRole("heading", { name: "Tariff search" })).toBeVisible();
  await expect(page.getByText("AA.00.0010").first()).toBeVisible();

  // The visual law: a frozen value renders in navy JetBrains Mono (.value-certified).
  const certified = page.locator(".value-certified").first();
  await expect(certified).toBeVisible();
  await expect(await certified.evaluate((el) => getComputedStyle(el).color)).toBe(NAVY);

  // 2. Master → detail.
  await page.getByText("AA.00.0010").first().click();
  await expect(page).toHaveURL(/\/tariffs\/TARDOC\/AA\.00\.0010/);
  await expect(page.getByText("Certified value")).toBeVisible();
  await expect(page.locator(".value-certified").first()).toBeVisible();
  // The frozen record carries a full SHA-256 in its hash chip title.
  await expect(page.getByTitle(/^[0-9a-f]{64}$/).first()).toBeVisible();

  // 3. Review form: submit against the mocked write path; the proposal becomes a frozen record.
  await page.goto("/review");
  await expect(page.getByText(/Flagged for review/)).toBeVisible();
  await page.getByRole("button", { name: /Approve proposal/ }).click();
  await expect(page.getByRole("heading", { name: "Frozen" })).toBeVisible();
  await expect(page.getByText(/v2/).first()).toBeVisible();

  // 4. Explain: the labelled AI surface. The label text is real CSS (::before), not markup.
  await page.goto("/explain");
  await page.getByLabel("tariff code").fill("AA.00.0010");
  await page.getByRole("button", { name: "Explain" }).click();
  const ai = page.locator(".ai-content").first();
  await expect(ai).toBeVisible();
  const label = await ai.evaluate((el) => getComputedStyle(el, "::before").content);
  expect(label).toContain("AI-generated");
});

test("capture console screenshots for the arc42 docs", async ({ page }) => {
  test.skip(!CAPTURE, "screenshot capture — run with CAPTURE=1");
  fs.mkdirSync(SHOT_DIR, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  const shot = (name: string) => page.screenshot({ path: path.join(SHOT_DIR, name), fullPage: true });

  // Home — the visual-law legend.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "TarifGuard Console" })).toBeVisible();
  await shot("home.png");

  // Master list.
  await page.goto("/search");
  await expect(page.getByText("AA.00.0010").first()).toBeVisible();
  await shot("master-list.png");

  // Detail — provenance + AI-assisted note + multilingual (SL medication with a price).
  await page.goto("/tariffs/SL/7680565740013");
  await expect(page.getByText(/AI-assisted/i)).toBeVisible();
  await expect(page.getByText("source document")).toBeVisible();
  await shot("detail-provenance.png");

  // Detail — version history (TARDOC, point-based).
  await page.goto("/tariffs/TARDOC/AA.00.0010");
  await expect(page.getByText(/Version history/i)).toBeVisible();
  await shot("detail-versions.png");

  // Review — raw vs ai_map proposal, side by side.
  await page.goto("/review");
  await expect(page.getByText(/Flagged for review/)).toBeVisible();
  await expect(page.getByText("ai_map proposal / correction")).toBeVisible();
  await shot("review-form.png");

  // Review — the proposal→frozen transition.
  await page.getByRole("button", { name: /Approve proposal/ }).click();
  await expect(page.getByRole("heading", { name: "Frozen" })).toBeVisible();
  await shot("review-frozen.png");

  // Explain — the labelled AI surface.
  await page.goto("/explain");
  await page.getByLabel("tariff code").fill("AA.00.0010");
  await page.getByRole("button", { name: "Explain" }).click();
  await expect(page.locator(".ai-content").first()).toBeVisible();
  await shot("explain-panel.png");
});
