import { expect, test } from "@playwright/test";
import {
  cleanupFakeRecorderArtifacts,
  ensureRecorderIdle,
  getRecordings,
  recorderState,
  refreshIndex,
} from "./helpers";

test.beforeEach(async ({ request }) => {
  await ensureRecorderIdle(request);
});

test.afterEach(async ({ request }) => {
  await ensureRecorderIdle(request);
  cleanupFakeRecorderArtifacts();
  await refreshIndex(request);
});

test("fake recorder starts from dialog, stops, selects latest, and opens enrichment", async ({ page, request }) => {
  await page.goto("/");
  await page.getByTestId("record-button").click();

  await page.getByTestId("start-recording-button").click();
  await expect(page.getByTestId("session-dialog").getByRole("heading", { name: "Recording" })).toBeVisible();
  await expect.poll(() => recorderState(request)).toBe("recording");
  await expect(page.getByTestId("stop-recording-button")).toBeVisible();

  await page.getByTestId("stop-recording-button").click();
  await expect(page.getByTestId("session-enrichment")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("session-enrichment").getByTestId("enrichment-form")).toBeVisible();

  const fakeRows = await getRecordings(request, { tag: "e2e" });
  expect(fakeRows.some((recording) => recording.id.startsWith("e2e-fake-"))).toBeTruthy();
});
