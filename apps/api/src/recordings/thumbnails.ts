import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { AppConfig } from "../config.js";

export type ThumbnailResult = {
  path: string;
  cached: boolean;
};

export type MediaInfo = {
  durationSeconds: number | null;
  sourceMtimeMs: number;
  sourceSizeBytes: number;
};

function cacheBaseName(id: string): string {
  return id.replace(/[^A-Za-z0-9._-]/g, "_");
}

function thumbnailCachePath(config: AppConfig, id: string): string {
  return path.join(config.thumbnailDir, `${cacheBaseName(id)}.jpg`);
}

function mediaInfoCachePath(config: AppConfig, id: string): string {
  return path.join(config.thumbnailDir, `${cacheBaseName(id)}.json`);
}

function isFresh(thumbnailPath: string, mediaPath: string): boolean {
  if (!fs.existsSync(thumbnailPath)) {
    return false;
  }
  const thumbnailStat = fs.statSync(thumbnailPath);
  const mediaStat = fs.statSync(mediaPath);
  return thumbnailStat.size > 0 && thumbnailStat.mtimeMs >= mediaStat.mtimeMs;
}

function readCachedMediaInfo(infoPath: string, mediaPath: string): MediaInfo | null {
  if (!fs.existsSync(infoPath)) {
    return null;
  }
  const mediaStat = fs.statSync(mediaPath);
  const parsed = JSON.parse(fs.readFileSync(infoPath, "utf8")) as Partial<MediaInfo>;
  if (
    typeof parsed.sourceMtimeMs === "number" &&
    typeof parsed.sourceSizeBytes === "number" &&
    parsed.sourceMtimeMs === mediaStat.mtimeMs &&
    parsed.sourceSizeBytes === mediaStat.size &&
    (typeof parsed.durationSeconds === "number" || parsed.durationSeconds === null)
  ) {
    return parsed as MediaInfo;
  }
  return null;
}

async function runThumbnailCommand(
  config: AppConfig,
  mediaPath: string,
  thumbnailPath: string,
): Promise<void> {
  const [command, ...baseArgs] = config.thumbnailCommand;
  const args = [
    ...baseArgs,
    "-y",
    "-ss",
    "00:00:01",
    "-i",
    mediaPath,
    "-frames:v",
    "1",
    "-vf",
    "scale=640:-1",
    thumbnailPath,
  ];

  await new Promise<void>((resolve, reject) => {
    const proc = spawn(command, args, { cwd: config.repoRoot });
    let stderr = "";
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    proc.on("error", reject);
    proc.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(new Error(stderr.trim() || `thumbnail command exited with code ${code}`));
    });
  });
}

async function probeDuration(config: AppConfig, mediaPath: string): Promise<number | null> {
  const [command, ...baseArgs] = config.ffprobeCommand;
  const args = [
    ...baseArgs,
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    mediaPath,
  ];

  return await new Promise<number | null>((resolve, reject) => {
    const proc = spawn(command, args, { cwd: config.repoRoot });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    proc.on("error", reject);
    proc.on("exit", (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `ffprobe exited with code ${code}`));
        return;
      }
      const parsed = JSON.parse(stdout || "{}") as {
        format?: { duration?: string | number };
      };
      const duration = Number(parsed.format?.duration);
      resolve(Number.isFinite(duration) && duration >= 0 ? duration : null);
    });
  });
}

export async function ensureThumbnail(
  config: AppConfig,
  id: string,
  mediaPath: string,
): Promise<ThumbnailResult> {
  const thumbnailPath = thumbnailCachePath(config, id);
  if (isFresh(thumbnailPath, mediaPath)) {
    return { path: thumbnailPath, cached: true };
  }

  fs.mkdirSync(config.thumbnailDir, { recursive: true });
  await runThumbnailCommand(config, mediaPath, thumbnailPath);

  if (!isFresh(thumbnailPath, mediaPath)) {
    throw new Error("thumbnail command did not create a fresh thumbnail");
  }
  return { path: thumbnailPath, cached: false };
}

export async function getMediaInfo(
  config: AppConfig,
  id: string,
  mediaPath: string,
): Promise<MediaInfo> {
  fs.mkdirSync(config.thumbnailDir, { recursive: true });
  const infoPath = mediaInfoCachePath(config, id);
  const cached = readCachedMediaInfo(infoPath, mediaPath);
  if (cached) {
    return cached;
  }

  const mediaStat = fs.statSync(mediaPath);
  const info: MediaInfo = {
    durationSeconds: await probeDuration(config, mediaPath),
    sourceMtimeMs: mediaStat.mtimeMs,
    sourceSizeBytes: mediaStat.size,
  };
  fs.writeFileSync(infoPath, `${JSON.stringify(info, null, 2)}\n`);
  return info;
}
