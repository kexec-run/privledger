import type { Database } from "../db/connection.js";

export function getCalendarMonth(db: Database, month: string) {
  const rows = db
    .prepare(
      `
      SELECT
        date_local,
        metadata_quality,
        has_transcript,
        mood,
        energy,
        stress,
        sleepiness,
        sleep_hours,
        caffeine_mg,
        tags_json
      FROM recordings
      WHERE date_local LIKE $month || '-%'
      ORDER BY date_local ASC
      `,
    )
    .all({ $month: month }) as Array<Record<string, unknown>>;

  const days = new Map<string, Array<Record<string, unknown>>>();
  for (const row of rows) {
    const date = row.date_local;
    if (typeof date !== "string") {
      continue;
    }
    days.set(date, [...(days.get(date) ?? []), row]);
  }

  return [...days.entries()].map(([dateLocal, dayRows]) => {
    const tags = new Set<string>();
    for (const row of dayRows) {
      try {
        const parsed = JSON.parse(String(row.tags_json ?? "[]")) as unknown;
        if (Array.isArray(parsed)) {
          for (const tag of parsed) {
            if (typeof tag === "string") {
              tags.add(tag);
            }
          }
        }
      } catch {
        // Cached tag JSON is derived and will be repaired by a later refresh.
      }
    }

    return {
      date_local: dateLocal,
      recording_count: dayRows.length,
      bad_count: dayRows.filter((row) => row.metadata_quality === "bad").length,
      good_count: dayRows.filter((row) => row.metadata_quality !== "bad").length,
      transcript_count: sum(dayRows, "has_transcript"),
      avg_mood: average(dayRows, "mood"),
      avg_energy: average(dayRows, "energy"),
      avg_stress: average(dayRows, "stress"),
      avg_sleepiness: average(dayRows, "sleepiness"),
      avg_sleep_hours: average(dayRows, "sleep_hours"),
      total_caffeine_mg: sumNullable(dayRows, "caffeine_mg"),
      tags: [...tags].sort(),
    };
  });
}

function average(rows: Array<Record<string, unknown>>, key: string): number | null {
  const values = rows
    .map((row) => row[key])
    .filter((value): value is number => typeof value === "number");
  if (values.length === 0) {
    return null;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function sum(rows: Array<Record<string, unknown>>, key: string): number {
  return rows.reduce(
    (total, row) => total + (typeof row[key] === "number" ? row[key] : 0),
    0,
  );
}

function sumNullable(rows: Array<Record<string, unknown>>, key: string): number | null {
  const values = rows
    .map((row) => row[key])
    .filter((value): value is number => typeof value === "number");
  if (values.length === 0) {
    return null;
  }
  return values.reduce((total, value) => total + value, 0);
}
