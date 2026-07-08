export type MetadataQuality = "basic" | "full" | "corrected" | "bad";

export type MetadataRecord = {
  id: string;
  timestamp_utc: string;
  timestamp_local?: string | null;
  schema_version: number;
  pipeline_version: string;
  metadata_quality: MetadataQuality;
  media_file: string;
  video_device?: string | null;
  transcript_file?: string | null;
  mood?: number | null;
  energy?: number | null;
  stress?: number | null;
  sleepiness?: number | null;
  sleep_hours?: number | null;
  caffeine_mg?: number | null;
  body_weight?: number | null;
  focus_domain?: string | null;
  tags?: string[];
  location?: string | null;
  custom?: unknown;
};

export type TranscriptSummary = {
  path: string | null;
  exists: boolean;
  language: string | null;
  segmentCount: number | null;
  textPreview: string | null;
  fullText: string | null;
  error: string | null;
};

export type IndexedRecording = {
  id: string;
  timestamp_utc: string | null;
  timestamp_local: string | null;
  date_local: string | null;
  schema_version: number | null;
  pipeline_version: string | null;
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
  custom_json: string | null;
  metadata_path: string;
  media_path: string | null;
  transcript_path: string | null;
  media_exists: number;
  transcript_exists: number;
  has_media: number;
  has_transcript: number;
  transcript_language: string | null;
  segment_count: number | null;
  text_preview: string | null;
  full_text: string | null;
  indexed_at: string;
  source_mtime_ms: number | null;
  source_size_bytes: number | null;
  index_status: "ok" | "invalid";
  index_error: string | null;
};

export type RefreshSummary = {
  scanned: number;
  indexed: number;
  invalid: number;
};
