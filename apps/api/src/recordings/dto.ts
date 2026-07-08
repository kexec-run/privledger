export type RecordingRow = Record<string, unknown> & {
  id: string;
  timestamp_utc: string | null;
  timestamp_local: string | null;
  date_local: string | null;
  metadata_quality: string | null;
  media_file: string | null;
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
  tags_json: string;
  location: string | null;
  media_exists: number;
  has_media: number;
  has_transcript: number;
  transcript_language: string | null;
  segment_count: number | null;
  text_preview: string | null;
  index_status: string;
  index_error: string | null;
};

function parseTags(tagsJson: string | null | undefined): string[] {
  if (!tagsJson) {
    return [];
  }
  try {
    const parsed = JSON.parse(tagsJson) as unknown;
    return Array.isArray(parsed)
      ? parsed.filter((tag): tag is string => typeof tag === "string")
      : [];
  } catch {
    return [];
  }
}

export function toRecordingSummary(row: RecordingRow) {
  return {
    id: row.id,
    startedAt: {
      utc: row.timestamp_utc,
      local: row.timestamp_local,
      dateLocal: row.date_local,
    },
    quality: row.metadata_quality,
    media: {
      file: row.media_file,
      exists: Boolean(row.has_media),
      url: row.has_media ? `/api/recordings/${row.id}/media` : null,
      thumbnailUrl: row.has_media ? `/api/recordings/${row.id}/thumbnail` : null,
      infoUrl: row.has_media ? `/api/recordings/${row.id}/media-info` : null,
      device: row.video_device,
    },
    transcript: {
      file: row.transcript_file,
      exists: Boolean(row.has_transcript),
      language: row.transcript_language,
      segmentCount: row.segment_count,
      preview: row.text_preview,
      url: row.has_transcript ? `/api/recordings/${row.id}/transcript` : null,
    },
    life: {
      mood: row.mood,
      energy: row.energy,
      stress: row.stress,
      sleepiness: row.sleepiness,
      sleepHours: row.sleep_hours,
      caffeineMg: row.caffeine_mg,
      bodyWeight: row.body_weight,
      focusDomain: row.focus_domain,
      tags: parseTags(row.tags_json),
      location: row.location,
    },
    index: {
      status: row.index_status,
      error: row.index_error,
    },
  };
}

export function toRecordingFull(row: RecordingRow) {
  return {
    ...toRecordingSummary(row),
    raw: {
      metadataUrl: `/api/recordings/${row.id}/metadata`,
      transcriptUrl: row.has_transcript
        ? `/api/recordings/${row.id}/transcript`
        : null,
    },
  };
}
