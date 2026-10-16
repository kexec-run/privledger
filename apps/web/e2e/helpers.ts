import { expect, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

export const repoRoot = path.resolve(process.cwd(), "../..");
export const vlogDir = path.join(repoRoot, "vlog");

export async function setFixtureDate(page: Page) {
  await page.clock.setFixedTime(new Date("2026-06-29T12:00:00+05:30"));
}

type RecordingSummary = {
  id: string;
  startedAt: {
    dateLocal: string;
    local: string | null;
  };
  life: {
    tags: string[];
  };
};

type MetadataFixture = {
  id: string;
  timestamp_utc: string;
  timestamp_local: string;
  schema_version: 1;
  pipeline_version: string;
  metadata_quality: "basic" | "full" | "corrected" | "bad";
  media_file: string;
  video_device: string | null;
  transcript_file: string | null;
  mood: number | null;
  energy: number | null;
  stress: number | null;
  sleepiness: number | null;
  sleep_hours: number | null;
  caffeine_mg: number | null;
  body_weight: number | null;
  focus_domain: string | null;
  tags: string[];
  location: string | null;
  custom?: null;
};

export function collectConsole(page: Page) {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      problems.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  return {
    assertClean() {
      expect(problems, problems.join("\n")).toEqual([]);
    },
  };
}

export async function refreshIndex(request: APIRequestContext) {
  const response = await request.post("/api/index/refresh");
  expect(response.ok()).toBeTruthy();
  return response.json();
}

export async function recorderState(request: APIRequestContext) {
  const response = await request.get("/api/status");
  expect(response.ok()).toBeTruthy();
  const status = await response.json();
  return status.recorder.state as string;
}

export async function ensureRecorderIdle(request: APIRequestContext) {
  const state = await recorderState(request);
  if (state === "recording" || state === "stopping") {
    await request.post("/api/recordings/stop");
    await expect.poll(() => recorderState(request), { timeout: 20_000 }).toBe("idle");
  }
}

export async function getRecordings(
  request: APIRequestContext,
  params: Record<string, string> = {},
) {
  const query = new URLSearchParams({ limit: "50", ...params });
  const response = await request.get(`/api/recordings?${query.toString()}`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()).recordings as RecordingSummary[];
}

export async function getFirstRecording(request: APIRequestContext) {
  const recordings = await getRecordings(request, { limit: "1" });
  expect(recordings.length).toBeGreaterThan(0);
  return recordings[0];
}

export async function openRecordingDay(page: Page, recording: RecordingSummary) {
  await page.getByTestId(`calendar-day-${recording.startedAt.dateLocal}`).click();
  await expect(page.getByRole("heading", { name: compactDate(recording.startedAt.dateLocal) })).toBeVisible();
}

export async function openFirstCard(page: Page) {
  const card = page.getByTestId("recording-card").first();
  await expect(card).toBeVisible();
  await card.click();
  await expect(page.getByTestId("inspector-panel")).toBeVisible();
}

export function writeRecordingFixture(
  id: string,
  overrides: Partial<MetadataFixture> = {},
) {
  fs.mkdirSync(vlogDir, { recursive: true });
  const base: MetadataFixture = {
    id,
    timestamp_utc: "2026-06-29T05:28:00.000Z",
    timestamp_local: "2026-06-29T10:58:00+05:30",
    schema_version: 1,
    pipeline_version: "e2e-fixture",
    metadata_quality: "basic",
    media_file: `${id}.mov`,
    video_device: "e2e-fixture",
    transcript_file: null,
    mood: 3,
    energy: 4,
    stress: 2,
    sleepiness: 1,
    sleep_hours: 7,
    caffeine_mg: null,
    body_weight: null,
    focus_domain: null,
    tags: ["e2e"],
    location: null,
    custom: undefined,
  };
  const metadata = { ...base, ...overrides };
  fs.writeFileSync(path.join(vlogDir, metadata.media_file), "fixture media\n");
  fs.writeFileSync(path.join(vlogDir, `${id}.json`), JSON.stringify(metadata, null, 2));
  return metadata;
}

export function cleanupRecordingFixture(id: string) {
  for (const suffix of [".json", ".mov"]) {
    fs.rmSync(path.join(vlogDir, `${id}${suffix}`), { force: true });
  }
}

export function cleanupFakeRecorderArtifacts() {
  const marker = path.join(repoRoot, ".privledger", "e2e-last-fake-id");
  if (!fs.existsSync(marker)) return null;
  const id = fs.readFileSync(marker, "utf8").trim();
  cleanupRecordingFixture(id);
  fs.rmSync(marker, { force: true });
  return id;
}

function compactDate(date: string) {
  const parsed = new Date(`${date}T00:00:00`);
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
