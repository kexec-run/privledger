import { expect, test } from "@playwright/test";
import { collectConsole, ensureRecorderIdle, getRecordings, inspectMedia, recorderState, repoRoot } from "./helpers";

test.beforeEach(async ({ request }) => {
  await ensureRecorderIdle(request);
});

test.afterEach(async ({ request }) => {
  await ensureRecorderIdle(request);
});

test("@real-recorder real capture saves basic metadata, enriches, and generates a thumbnail", async ({ page, request }) => {
  const consoleHealth = collectConsole(page);
  const before = await getRecordings(request, { limit: "1" });

  await page.goto("/");
  await page.getByTestId("record-button").click();
  await expect(page.getByRole("heading", { name: "Prepare recording" })).toBeVisible();

  await page.getByTestId("start-recording-button").click();
  await expect.poll(() => recorderState(request), { timeout: 20_000 }).toBe("recording");
  await expect(page.getByTestId("session-dialog").getByRole("heading", { name: "Recording" })).toBeVisible();

  await page.waitForTimeout(10_000);
  await page.getByTestId("stop-recording-button").click();
  await expect(page.getByTestId("session-enrichment")).toBeVisible({ timeout: 60_000 });
  await expect.poll(() => recorderState(request), { timeout: 20_000 }).toBe("idle");

  const after = await getRecordings(request, { limit: "1" });
  expect(after[0]?.id).toBeTruthy();
  expect(after[0]?.id).not.toEqual(before[0]?.id);
  expect(after[0]?.media.file).toBeTruthy();
  const mediaPath = `${repoRoot}/vlog/${after[0].media.file}`;
  const media = inspectMedia(mediaPath);
  expect(media.durationSeconds).toBeGreaterThan(1);
  expect(media.codecs.length).toBeGreaterThan(0);
  console.log(`Real media: ${media.durationSeconds.toFixed(2)}s (${media.codecs.join(", ")})`);

  const metadataUrl = `/api/recordings/${after[0].id}/metadata`;
  const basicResponse = await request.get(metadataUrl);
  expect(basicResponse.ok()).toBeTruthy();
  expect((await basicResponse.json()).metadata_quality).toBe("basic");
  await expect(page.getByTestId("enrichment-form")).toHaveCount(1);
  await page.getByTestId("enrichment-input-mood").fill("4");
  await page.getByTestId("enrichment-input-sleep_hours").fill("7.5");
  await page.getByTestId("save-enrichment-button").click();
  await expect(page.getByTestId("session-dialog")).toHaveCount(0);
  const enrichedResponse = await request.get(metadataUrl);
  expect(enrichedResponse.ok()).toBeTruthy();
  expect(await enrichedResponse.json()).toMatchObject({ mood: 4, sleep_hours: 7.5 });

  const infoResponse = await request.get(`/api/recordings/${after[0].id}/media-info`);
  expect(infoResponse.ok()).toBeTruthy();
  const info = await infoResponse.json();
  expect(info.durationSeconds).toBeGreaterThan(1);
  const thumbnailResponse = await request.get(info.thumbnailUrl);
  expect(thumbnailResponse.ok()).toBeTruthy();
  expect(thumbnailResponse.headers()["content-type"]).toContain("image/");
  expect((await thumbnailResponse.body()).length).toBeGreaterThan(0);
  const latestCard = page.locator(`[data-recording-id="${after[0].id}"]`);
  await expect(latestCard).toBeVisible({ timeout: 20_000 });
  await latestCard.click();
  await expect(page.getByTestId("inspector-panel")).toBeVisible();
  await expect(page.getByTestId("life-metadata-block")).toBeVisible();
  consoleHealth.assertClean();
});
