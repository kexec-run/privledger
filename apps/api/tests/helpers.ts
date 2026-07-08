import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createConfig } from "../src/config.js";
import { openDatabase } from "../src/db/connection.js";

export function createTestContext() {
  const repoRoot = fs.mkdtempSync(path.join(os.tmpdir(), "privledger-api-"));
  const vlogDir = path.join(repoRoot, "vlog");
  const transcriptDir = path.join(vlogDir, "transcripts");
  fs.mkdirSync(transcriptDir, { recursive: true });
  fs.mkdirSync(path.join(repoRoot, "scripts"), { recursive: true });
  const config = createConfig({
    repoRoot,
    vlogDir,
    transcriptDir,
    dbPath: path.join(repoRoot, ".privledger", "test.sqlite"),
    thumbnailDir: path.join(repoRoot, ".privledger", "thumbnails"),
    recordCommand: ["python3", path.join(repoRoot, "scripts", "privledger.py")],
    enrichCommand: ["python3", path.join(repoRoot, "scripts", "enrich.py")],
    thumbnailCommand: ["ffmpeg"],
    ffprobeCommand: ["ffprobe"],
    transcribeCommand: [
      "python3",
      path.join(repoRoot, "scripts", "transcript_batch.py"),
      "transcribe",
      "--apply",
    ],
  });
  const db = openDatabase(config.dbPath);
  return { repoRoot, vlogDir, transcriptDir, config, db };
}

export function writeJson(pathname: string, payload: unknown) {
  fs.mkdirSync(path.dirname(pathname), { recursive: true });
  fs.writeFileSync(pathname, `${JSON.stringify(payload, null, 2)}\n`);
}

export function baseMetadata(overrides: Record<string, unknown> = {}) {
  return {
    id: "2026-06-29-0930",
    timestamp_utc: "2026-06-29T04:00:00Z",
    timestamp_local: "2026-06-29T09:30:00+05:30",
    schema_version: 1,
    pipeline_version: "0.1.0",
    metadata_quality: "full",
    media_file: "2026-06-29-0930.mov",
    video_device: "brio",
    transcript_file: "transcripts/2026-06-29-0930.whisper-large-v3-source.json",
    mood: 3,
    energy: 4,
    stress: 2,
    sleepiness: 1,
    sleep_hours: 7.5,
    caffeine_mg: 120,
    body_weight: 70.2,
    focus_domain: "work",
    tags: ["work", "planning"],
    location: "desk",
    custom: { schema_hash: "abcdef123456", data: { marker: true } },
    ...overrides,
  };
}

export function transcriptPayload() {
  return {
    result: { language: "en" },
    transcription: [
      {
        timestamps: { from: "00:00:00,000", to: "00:00:01,000" },
        offsets: { from: 0, to: 1000 },
        text: "hello privledger",
      },
    ],
  };
}
