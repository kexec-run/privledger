import { expect, test } from "@playwright/test";
import {
  cleanupRecordingFixture,
  collectConsole,
  refreshIndex,
  setFixtureDate,
  writeRecordingFixture,
} from "./helpers";

const screenshotFixtureId = "e2e-screenshot";

test.beforeEach(async ({ page }) => {
  await setFixtureDate(page);
});

test.afterEach(async ({ request }) => {
  cleanupRecordingFixture(screenshotFixtureId);
  await refreshIndex(request);
});

test("dashboard shell renders core regions", async ({ page, request }) => {
  const consoleState = collectConsole(page);
  await refreshIndex(request);

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Privledger" })).toBeVisible();
  await expect(page.getByTestId("record-button")).toBeVisible();
  await expect(page.getByTestId("screenshot-mode-button")).toBeVisible();
  await expect(page.getByTestId("refresh-index-button")).toBeVisible();
  await expect(page.getByText("Calendar")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Tags" })).toBeVisible();
  await expect(page.getByText("Index size")).toBeVisible();
  await expect(page.getByTestId("inspector-panel")).toBeVisible();
  await expect(page.getByLabel("Open menu")).toHaveCount(0);

  consoleState.assertClean();
});

test("screenshot mode toggles privacy affordance", async ({ page, request }) => {
  writeRecordingFixture(screenshotFixtureId, {
    timestamp_utc: "2026-06-29T05:31:00.000Z",
    timestamp_local: "2026-06-29T11:01:00+05:30",
    tags: [],
    video_device: "screenshot-device",
  });
  await refreshIndex(request);
  await page.goto("/");
  await page.getByTestId("calendar-day-2026-06-29").click();
  await page.getByTestId("recording-card").filter({ hasText: "screenshot-device" }).click();

  const button = page.getByTestId("screenshot-mode-button");
  await expect(button).toBeVisible();
  await button.click();
  await expect(button).toHaveClass(/active/);
  await expect(page.locator(".video-preview.privacy-blur").first()).toBeVisible();

  await button.click();
  await expect(button).not.toHaveClass(/active/);
});
