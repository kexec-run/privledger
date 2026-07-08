import fs from "node:fs";
import type { MetadataRecord } from "./types.js";

const qualityValues = new Set(["basic", "full", "corrected", "bad"]);

export function readMetadata(path: string): MetadataRecord {
  const parsed = JSON.parse(fs.readFileSync(path, "utf8")) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("metadata must be a JSON object");
  }

  const metadata = parsed as Record<string, unknown>;
  for (const key of [
    "id",
    "timestamp_utc",
    "schema_version",
    "pipeline_version",
    "metadata_quality",
    "media_file",
  ]) {
    if (!(key in metadata)) {
      throw new Error(`metadata missing required field: ${key}`);
    }
  }

  if (typeof metadata.id !== "string" || metadata.id.length === 0) {
    throw new Error("metadata id must be a non-empty string");
  }
  if (
    typeof metadata.metadata_quality !== "string" ||
    !qualityValues.has(metadata.metadata_quality)
  ) {
    throw new Error("metadata_quality is missing or unknown");
  }
  if (typeof metadata.media_file !== "string" || metadata.media_file.length === 0) {
    throw new Error("media_file must be a non-empty string");
  }

  return metadata as MetadataRecord;
}
