import fs from "node:fs";
import path from "node:path";
import type { Database } from "../db/connection.js";
import { resolveInside, resolveTranscriptPath } from "../files/safePath.js";
import type { AppConfig } from "../config.js";
import { readMetadata } from "./readMetadata.js";
import { readTranscriptSummary } from "./readTranscript.js";
import type { IndexedRecording, MetadataRecord, RefreshSummary } from "./types.js";

function toDateLocal(metadata: MetadataRecord): string | null {
  const source = metadata.timestamp_local ?? metadata.timestamp_utc;
  if (!source || typeof source !== "string") {
    return null;
  }
  return source.slice(0, 10);
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function buildInvalidRow(
  metadataPath: string,
  error: unknown,
  indexedAt: string,
): IndexedRecording {
  const stat = fs.statSync(metadataPath);
  const id = path.basename(metadataPath, ".json");
  return {
    id,
    timestamp_utc: null,
    timestamp_local: null,
    date_local: null,
    schema_version: null,
    pipeline_version: null,
    metadata_quality: null,
    media_file: null,
    video_device: null,
    transcript_file: null,
    mood: null,
    energy: null,
    stress: null,
    sleepiness: null,
    sleep_hours: null,
    caffeine_mg: null,
    body_weight: null,
    focus_domain: null,
    tags_json: "[]",
    location: null,
    custom_json: null,
    metadata_path: metadataPath,
    media_path: null,
    transcript_path: null,
    media_exists: 0,
    transcript_exists: 0,
    has_media: 0,
    has_transcript: 0,
    transcript_language: null,
    segment_count: null,
    text_preview: null,
    full_text: null,
    indexed_at: indexedAt,
    source_mtime_ms: Math.round(stat.mtimeMs),
    source_size_bytes: stat.size,
    index_status: "invalid",
    index_error: error instanceof Error ? error.message : String(error),
  };
}

export function buildRecordingRow(
  config: AppConfig,
  metadataPath: string,
  indexedAt: string,
): IndexedRecording {
  const stat = fs.statSync(metadataPath);
  const metadata = readMetadata(metadataPath);
  const mediaPath = resolveInside(config.vlogDir, metadata.media_file);
  const mediaExists =
    metadata.metadata_quality !== "bad" && mediaPath !== null && fs.existsSync(mediaPath);
  const transcriptPath = resolveTranscriptPath(
    config.vlogDir,
    config.transcriptDir,
    metadata.transcript_file,
  );
  const transcript = readTranscriptSummary(transcriptPath);
  const transcriptError = transcript.error
    ? `transcript invalid: ${transcript.error}`
    : null;

  return {
    id: metadata.id,
    timestamp_utc: metadata.timestamp_utc,
    timestamp_local: nullableString(metadata.timestamp_local),
    date_local: toDateLocal(metadata),
    schema_version: metadata.schema_version,
    pipeline_version: metadata.pipeline_version,
    metadata_quality: metadata.metadata_quality,
    media_file: metadata.media_file,
    video_device: nullableString(metadata.video_device),
    transcript_file: nullableString(metadata.transcript_file),
    mood: nullableNumber(metadata.mood),
    energy: nullableNumber(metadata.energy),
    stress: nullableNumber(metadata.stress),
    sleepiness: nullableNumber(metadata.sleepiness),
    sleep_hours: nullableNumber(metadata.sleep_hours),
    caffeine_mg: nullableNumber(metadata.caffeine_mg),
    body_weight: nullableNumber(metadata.body_weight),
    focus_domain: nullableString(metadata.focus_domain),
    tags_json: JSON.stringify(Array.isArray(metadata.tags) ? metadata.tags : []),
    location: nullableString(metadata.location),
    custom_json:
      metadata.custom === undefined || metadata.custom === null
        ? null
        : JSON.stringify(metadata.custom),
    metadata_path: metadataPath,
    media_path: mediaPath,
    transcript_path: transcript.path,
    media_exists: mediaExists ? 1 : 0,
    transcript_exists: transcript.exists ? 1 : 0,
    has_media: mediaExists ? 1 : 0,
    has_transcript: transcript.exists && transcriptError === null ? 1 : 0,
    transcript_language: transcript.language,
    segment_count: transcript.segmentCount,
    text_preview: transcript.textPreview,
    full_text: transcript.fullText,
    indexed_at: indexedAt,
    source_mtime_ms: Math.round(stat.mtimeMs),
    source_size_bytes: stat.size,
    index_status: transcriptError ? "invalid" : "ok",
    index_error: transcriptError,
  };
}

const columns = [
  "id",
  "timestamp_utc",
  "timestamp_local",
  "date_local",
  "schema_version",
  "pipeline_version",
  "metadata_quality",
  "media_file",
  "video_device",
  "transcript_file",
  "mood",
  "energy",
  "stress",
  "sleepiness",
  "sleep_hours",
  "caffeine_mg",
  "body_weight",
  "focus_domain",
  "tags_json",
  "location",
  "custom_json",
  "metadata_path",
  "media_path",
  "transcript_path",
  "media_exists",
  "transcript_exists",
  "has_media",
  "has_transcript",
  "transcript_language",
  "segment_count",
  "text_preview",
  "full_text",
  "indexed_at",
  "source_mtime_ms",
  "source_size_bytes",
  "index_status",
  "index_error",
] as const;

function upsertRecording(db: Database, row: IndexedRecording): void {
  const placeholders = columns.map((column) => `$${column}`).join(", ");
  const assignments = columns
    .filter((column) => column !== "id")
    .map((column) => `${column}=excluded.${column}`)
    .join(", ");
  const statement = db.prepare(
    `INSERT INTO recordings (${columns.join(", ")})
     VALUES (${placeholders})
     ON CONFLICT(id) DO UPDATE SET ${assignments}`,
  );
  statement.run(
    Object.fromEntries(columns.map((column) => [`$${column}`, row[column]])),
  );

  db.prepare("DELETE FROM recordings_fts WHERE id = ?").run(row.id);
  if (row.full_text || row.text_preview) {
    db.prepare(
      "INSERT INTO recordings_fts (id, full_text, text_preview) VALUES (?, ?, ?)",
    ).run(row.id, row.full_text ?? "", row.text_preview ?? "");
  }
}

export function refreshIndex(db: Database, config: AppConfig): RefreshSummary {
  fs.mkdirSync(config.vlogDir, { recursive: true });
  const metadataFiles = fs
    .readdirSync(config.vlogDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(config.vlogDir, entry.name))
    .sort();

  let indexed = 0;
  let invalid = 0;
  const indexedAt = new Date().toISOString();
  const seenIds = new Set<string>();

  db.exec("BEGIN");
  try {
    for (const metadataPath of metadataFiles) {
      let row: IndexedRecording;
      try {
        row = buildRecordingRow(config, metadataPath, indexedAt);
      } catch (error) {
        row = buildInvalidRow(metadataPath, error, indexedAt);
      }
      upsertRecording(db, row);
      seenIds.add(row.id);
      if (row.index_status === "ok") {
        indexed += 1;
      } else {
        invalid += 1;
      }
    }

    const existing = db.prepare("SELECT id FROM recordings").all() as Array<{
      id: string;
    }>;
    for (const row of existing) {
      if (!seenIds.has(row.id)) {
        db.prepare("DELETE FROM recordings WHERE id = ?").run(row.id);
        db.prepare("DELETE FROM recordings_fts WHERE id = ?").run(row.id);
      }
    }
    db.exec("COMMIT");
  } catch (error) {
    db.exec("ROLLBACK");
    throw error;
  }

  return { scanned: metadataFiles.length, indexed, invalid };
}
