import { expect, test } from "@playwright/test";
import { ensureRecorderIdle, recorderState } from "./helpers";

test.beforeEach(async ({ request }) => {
  await ensureRecorderIdle(request);
});

test.afterEach(async ({ request }) => {
  await ensureRecorderIdle(request);
});

test("record button opens prepare mode without starting recorder", async ({ page, request }) => {
  await page.goto("/");

  await page.getByTestId("record-button").click();
  await expect(page.getByTestId("session-dialog")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Prepare recording" })).toBeVisible();
  await expect(page.getByText("Recorder not started")).toBeVisible();
  await expect(page.getByTestId("start-recording-button")).toBeVisible();
  await expect(page.getByTestId("stop-recording-button")).toHaveCount(0);
  await expect.poll(() => recorderState(request)).toBe("idle");

  await page.getByTestId("cancel-recording-button").click();
  await expect(page.getByTestId("session-dialog")).toHaveCount(0);
  await expect.poll(() => recorderState(request)).toBe("idle");
});

test("guide accordion expands, collapses, and preserves ordering", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("record-button").click();

  const sections = page.getByTestId("guide-section-title");
  const count = await sections.count();
  expect(count).toBeGreaterThan(1);
  const before = await sections.allTextContents();

  let collapsedIndex = -1;
  for (let index = 0; index < count; index += 1) {
    if ((await sections.nth(index).getAttribute("aria-expanded")) === "false") {
      collapsedIndex = index;
      break;
    }
  }
  expect(collapsedIndex).toBeGreaterThanOrEqual(0);

  await sections.nth(collapsedIndex).click();
  await expect(sections.nth(collapsedIndex)).toHaveAttribute("aria-expanded", "true");

  await sections.nth(collapsedIndex).click();
  await expect(sections.nth(collapsedIndex)).toHaveAttribute("aria-expanded", "false");
  await expect.poll(() => sections.allTextContents()).toEqual(before);
});
