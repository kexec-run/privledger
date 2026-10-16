import { expect, test } from "@playwright/test";
import {
  cleanupRecordingFixture,
  openFirstCard,
  refreshIndex,
  setFixtureDate,
  writeRecordingFixture,
} from "./helpers";

const fixtureIds = ["e2e-inspector-a", "e2e-inspector-b"];

test.beforeEach(async ({ page }) => {
  await setFixtureDate(page);
});

test.afterEach(async ({ request }) => {
  fixtureIds.forEach(cleanupRecordingFixture);
  await refreshIndex(request);
});

test("recording list sorting, inspector, media, and metadata controls work", async ({ page, request }) => {
  writeRecordingFixture("e2e-inspector-a", {
    timestamp_utc: "2026-06-29T04:50:00.000Z",
    timestamp_local: "2026-06-29T10:20:00+05:30",
    tags: ["e2e-inspector"],
  });
  writeRecordingFixture("e2e-inspector-b", {
    timestamp_utc: "2026-06-29T05:28:00.000Z",
    timestamp_local: "2026-06-29T10:58:00+05:30",
    tags: ["e2e-inspector"],
  });
  await refreshIndex(request);

  await page.goto("/");
  await page.getByTestId("calendar-day-2026-06-29").click();
  await page.getByTestId("tag-row").filter({ hasText: "e2e-inspector" }).click();

  const firstBefore = await page.getByTestId("recording-card").first().innerText();
  await page.locator(".sort-button").click();
  const firstAfter = await page.getByTestId("recording-card").first().innerText();
  expect(firstAfter).not.toEqual(firstBefore);

  await openFirstCard(page);
  await expect(page.getByTestId("media-block")).toContainText(/Media available|Media missing/);
  await expect(page.getByTestId("media-block").getByRole("button")).toHaveCount(0);
  await expect(page.getByTestId("life-metadata-block")).toContainText("mood");

  await page.getByLabel("Close inspector").click();
  await expect(page.getByText("Select a recording")).toBeVisible();

  await openFirstCard(page);
  await page.getByTestId("metadata-toggle").click();
  await expect(page.locator(".metadata-preview")).toContainText("e2e-inspector");
});
