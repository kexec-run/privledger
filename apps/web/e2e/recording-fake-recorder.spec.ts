import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
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
  const captureDir = process.env.PRIVLEDGER_E2E_CAPTURE_DIR;
  if (captureDir) {
    await page.setViewportSize({ width: 1680, height: 1440 });
    fs.mkdirSync(captureDir, { recursive: true });
  }
  await page.goto("/");
  await page.getByTestId("record-button").click();
  await expect(page.getByRole("heading", { name: "Prepare recording" })).toBeVisible();
  if (captureDir) {
    await page.screenshot({ path: path.join(captureDir, "recording-guide.png"), fullPage: true });
  }

  await page.getByTestId("start-recording-button").click();
  await expect(page.getByTestId("session-dialog").getByRole("heading", { name: "Recording" })).toBeVisible();
  await expect.poll(() => recorderState(request)).toBe("recording");
  await expect(page.getByTestId("stop-recording-button")).toBeVisible();
  await expect.poll(async () => {
    const response = await request.get("/api/status");
    return (await response.json()).recorder.recentLogs as string[];
  }).toContain("fake-recorder: ready");

  await page.getByTestId("stop-recording-button").click();
  await expect(page.getByTestId("session-enrichment")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId("session-enrichment").getByTestId("enrichment-form")).toBeVisible();
  await expect(page.getByTestId("session-enrichment").getByTestId("save-enrichment-button")).toBeVisible();
  await expect(page.getByTestId("enrichment-form")).toHaveCount(1);
  if (captureDir) {
    await page.screenshot({ path: path.join(captureDir, "enrichment-dialog.png"), fullPage: true });
  }

  const fakeRows = await getRecordings(request, { tag: "e2e" });
  expect(fakeRows.some((recording) => recording.id.startsWith("e2e-fake-"))).toBeTruthy();

  await page.getByRole("button", { name: "Enrich later" }).click();
  await expect(page.getByTestId("session-dialog")).toHaveCount(0);
  await page.getByTestId("enrich-metadata-button").click();
  await expect(page.getByTestId("enrichment-form")).toBeVisible();
  await expect(page.getByTestId("enrichment-form")).toHaveCount(1);

});
