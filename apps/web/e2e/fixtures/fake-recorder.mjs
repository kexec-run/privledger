import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = process.env.PRIVLEDGER_ROOT ?? path.resolve(here, "../../../..");
const vlogDir = path.join(repoRoot, "vlog");
const cacheDir = path.join(repoRoot, ".privledger");

function pad(value) {
  return String(value).padStart(2, "0");
}

function buildId(date) {
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join("-") + `-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

function writeRecording() {
  fs.mkdirSync(vlogDir, { recursive: true });
  fs.mkdirSync(cacheDir, { recursive: true });

  const now = new Date();
  const id = `e2e-fake-${buildId(now)}`;
  const mediaFile = `${id}.mov`;
  const metadata = {
    id,
    timestamp_utc: now.toISOString(),
    timestamp_local: now.toISOString(),
    schema_version: 1,
    pipeline_version: "e2e-fake",
    metadata_quality: "basic",
    media_file: mediaFile,
    video_device: "fake-recorder",
    transcript_file: null,
    mood: null,
    energy: null,
    stress: null,
    sleepiness: null,
    sleep_hours: null,
    caffeine_mg: null,
    body_weight: null,
    focus_domain: null,
    tags: ["e2e"],
    location: null,
    custom: null,
  };

  fs.writeFileSync(path.join(vlogDir, mediaFile), "fake media\n");
  fs.writeFileSync(path.join(vlogDir, `${id}.json`), JSON.stringify(metadata, null, 2));
  fs.writeFileSync(path.join(cacheDir, "e2e-last-fake-id"), id);
}

let stopped = false;

function stop() {
  if (stopped) return;
  stopped = true;
  writeRecording();
  process.exit(0);
}

process.on("SIGINT", stop);
process.on("SIGTERM", stop);
setInterval(() => {}, 1000);
console.log("fake-recorder: ready");
