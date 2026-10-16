import { expect, test } from "@playwright/test";
import {
  cleanupRecordingFixture,
  refreshIndex,
  setFixtureDate,
  writeRecordingFixture,
} from "./helpers";

const fixtureIds = ["e2e-calendar-a", "e2e-calendar-b"];

test.beforeEach(async ({ page }) => {
  await setFixtureDate(page);
});

test.afterEach(async ({ request }) => {
  fixtureIds.forEach(cleanupRecordingFixture);
  await refreshIndex(request);
});

test("calendar navigation, date selection, and tag filters are isolated", async ({ page, request }) => {
  writeRecordingFixture("e2e-calendar-a", {
    timestamp_utc: "2026-06-29T05:28:00.000Z",
    timestamp_local: "2026-06-29T10:58:00+05:30",
    tags: ["e2e-calendar", "planning"],
  });
  writeRecordingFixture("e2e-calendar-b", {
    timestamp_utc: "2026-06-16T04:00:00.000Z",
    timestamp_local: "2026-06-16T09:30:00+05:30",
    tags: ["e2e-calendar"],
  });
  await refreshIndex(request);

  await page.goto("/");
  await page.getByLabel("Previous month").click();
  await expect(page.getByRole("heading", { name: /May 2026|June 2026|Jul 2026/ })).toBeVisible();
  await page.getByLabel("Next month").click();
  await page.getByTestId("calendar-day-2026-06-29").click();

  await expect(page.getByRole("heading", { name: "Jun 29" })).toBeVisible();
  await expect(page.getByTestId("recording-card").filter({ hasText: "e2e-calendar" })).toBeVisible();

  await page.getByTestId("tag-row").filter({ hasText: "e2e-calendar" }).click();
  await expect(page.getByText("matching e2e-calendar")).toBeVisible();

  await page.getByTestId("tag-row-all").click();
  await expect(page.locator(".day-header")).toContainText("recordings");
});

test("empty day state renders independently from filters", async ({ page, request }) => {
  await refreshIndex(request);
  await page.goto("/");
  await page.getByLabel("Previous month").click();
  await page.getByLabel("Previous month").click();
  await page.getByTestId("calendar-day-2026-05-01").click();

  await expect(page.getByRole("heading", { name: "May 1" })).toBeVisible();
  await expect(page.getByText("No recordings for this filter")).toBeVisible();
});
