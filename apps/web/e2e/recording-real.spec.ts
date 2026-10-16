import { expect, test } from "@playwright/test";
import { ensureRecorderIdle, getRecordings, inspectMedia, recorderState, repoRoot } from "./helpers";

test.beforeEach(async ({ request }) => {
  await ensureRecorderIdle(request);
});

test.afterEach(async ({ request }) => {
  await ensureRecorderIdle(request);
});

test("@real-recorder real Python recorder starts and stops from the UI", async ({ page, request }) => {
  const before = await getRecordings(request, { limit: "1" });

  await page.goto("/");
  await page.getByTestId("record-button").click();
  await expect(page.getByRole("heading", { name: "Prepare recording" })).toBeVisible();

  await page.getByTestId("start-recording-button").click();
  await expect.poll(() => recorderState(request), { timeout: 20_000 }).toBe("recording");
  await expect(page.getByTestId("session-dialog").getByRole("heading", { name: "Recording" })).toBeVisible();

  await page.waitForTimeout(3_000);
  await page.getByTestId("stop-recording-button").click();
  await expect(page.getByTestId("session-enrichment")).toBeVisible({ timeout: 60_000 });
  await expect.poll(() => recorderState(request), { timeout: 20_000 }).toBe("idle");

  const after = await getRecordings(request, { limit: "1" });
  expect(after[0]?.id).toBeTruthy();
  expect(after[0]?.id).not.toEqual(before[0]?.id);
  expect(after[0]?.media.file).toBeTruthy();
  const mediaPath = `${repoRoot}/vlog/${after[0].media.file}`;
  const media = inspectMedia(mediaPath);
  expect(media.durationSeconds).toBeGreaterThan(0);
  expect(media.codecs.length).toBeGreaterThan(0);
  console.log(`Real media: ${media.durationSeconds.toFixed(2)}s (${media.codecs.join(", ")})`);

  await page.getByLabel("Close session dialog").click();
  const latestCard = page.locator(`[data-recording-id="${after[0].id}"]`);
  await expect(latestCard).toBeVisible({ timeout: 20_000 });
  await latestCard.click();
  await expect(page.getByTestId("inspector-panel")).toBeVisible();
  await expect(page.getByTestId("life-metadata-block")).toBeVisible();
});
