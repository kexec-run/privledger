import { expect, test } from "@playwright/test";
import {
  cleanupRecordingFixture,
  refreshIndex,
  setFixtureDate,
  writeRecordingFixture,
} from "./helpers";

const fixtureId = "e2e-enrichment";

test.beforeEach(async ({ page }) => {
  await setFixtureDate(page);
});

test.afterEach(async ({ request }) => {
  cleanupRecordingFixture(fixtureId);
  await refreshIndex(request);
});

test("enrichment submit highlights rejected field and accepts valid correction", async ({ page, request }) => {
  writeRecordingFixture(fixtureId, {
    timestamp_utc: "2026-06-29T05:29:00.000Z",
    timestamp_local: "2026-06-29T10:59:00+05:30",
    tags: [],
    video_device: "enrichment-device",
  });
  await refreshIndex(request);

  await page.goto("/");
  await page.getByTestId("calendar-day-2026-06-29").click();
  await page.getByTestId("recording-card").filter({ hasText: "enrichment-device" }).click();
  await page.getByTestId("enrich-metadata-button").click();
  await expect(page.getByTestId("enrichment-form")).toBeVisible();

  const moodInput = page.getByTestId("enrichment-input-mood");
  await moodInput.fill("99");
  await expect(moodInput).toHaveValue("99");
  await page.getByTestId("save-enrichment-button").click();

  await expect(page.locator(".enrichment-error")).toBeVisible();
  await expect(page.getByTestId("enrichment-field-mood")).toHaveClass(/invalid-field/);
  await expect(moodInput).toHaveValue("99");

  await moodInput.fill("4");
  await page.getByTestId("save-enrichment-button").click();
  await expect(page.locator(".enrichment-error")).toHaveCount(0);
  await expect(page.getByTestId("enrichment-form")).toHaveCount(0);
});
