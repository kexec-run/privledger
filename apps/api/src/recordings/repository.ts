import fs from "node:fs";
import type { Database } from "../db/connection.js";

export type RecordingFilters = {
  date?: string;
  from?: string;
  to?: string;
  metadata_quality?: string;
  has_transcript?: boolean;
  tag?: string;
  q?: string;
  limit: number;
  offset: number;
};

export function listRecordings(db: Database, filters: RecordingFilters) {
  const where: string[] = [];
  const params: Record<string, string | number> = {
    $limit: filters.limit,
    $offset: filters.offset,
  };

  if (filters.date) {
    where.push("date_local = $date");
    params.$date = filters.date;
  }
  if (filters.from) {
    where.push("date_local >= $from");
    params.$from = filters.from;
  }
  if (filters.to) {
    where.push("date_local <= $to");
    params.$to = filters.to;
  }
  if (filters.metadata_quality) {
    where.push("metadata_quality = $quality");
    params.$quality = filters.metadata_quality;
  }
  if (filters.has_transcript !== undefined) {
    where.push("has_transcript = $hasTranscript");
    params.$hasTranscript = filters.has_transcript ? 1 : 0;
  }
  if (filters.tag) {
    where.push("tags_json LIKE $tag");
    params.$tag = `%"${filters.tag}"%`;
  }
  if (filters.q) {
    where.push(
      "id IN (SELECT id FROM recordings_fts WHERE recordings_fts MATCH $q)",
    );
    params.$q = filters.q;
  }

  const sql = `SELECT * FROM recordings ${
    where.length ? `WHERE ${where.join(" AND ")}` : ""
  } ORDER BY timestamp_utc DESC, id DESC LIMIT $limit OFFSET $offset`;
  return db.prepare(sql).all(params);
}

export function getRecording(db: Database, id: string) {
  return db.prepare("SELECT * FROM recordings WHERE id = ?").get(id) ?? null;
}

export function readJsonFile(path: string | null) {
  if (!path || !fs.existsSync(path)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(path, "utf8")) as unknown;
}

export function getFacets(db: Database) {
  const rows = db
    .prepare(
      "SELECT tags_json, focus_domain, metadata_quality, date_local FROM recordings",
    )
    .all() as Array<{
    tags_json: string | null;
    focus_domain: string | null;
    metadata_quality: string | null;
    date_local: string | null;
  }>;

  const tagCounts = new Map<string, number>();
  const focusDomains = new Set<string>();
  const qualities = new Set<string>();
  const dates = rows
    .map((row) => row.date_local)
    .filter((date): date is string => typeof date === "string")
    .sort();

  for (const row of rows) {
    if (row.focus_domain) {
      focusDomains.add(row.focus_domain);
    }
    if (row.metadata_quality) {
      qualities.add(row.metadata_quality);
    }
    try {
      const parsed = JSON.parse(row.tags_json ?? "[]") as unknown;
      if (Array.isArray(parsed)) {
        for (const tag of parsed) {
          if (typeof tag === "string") {
            tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1);
          }
        }
      }
    } catch {
      // Ignore malformed cached tag JSON; source JSON will repair on refresh.
    }
  }

  return {
    tags: [...tagCounts.entries()]
      .sort(([leftTag, leftCount], [rightTag, rightCount]) =>
        rightCount - leftCount || leftTag.localeCompare(rightTag),
      )
      .map(([tag]) => tag),
    tagCounts: Object.fromEntries(tagCounts),
    focusDomains: [...focusDomains].sort(),
    qualities: [...qualities].sort(),
    dateRange: {
      from: dates[0] ?? null,
      to: dates.at(-1) ?? null,
    },
  };
}
