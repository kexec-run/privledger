PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS recordings (
  id TEXT PRIMARY KEY,
  timestamp_utc TEXT,
  timestamp_local TEXT,
  date_local TEXT,
  schema_version INTEGER,
  pipeline_version TEXT,
  metadata_quality TEXT,
  media_file TEXT,
  video_device TEXT,
  transcript_file TEXT,
  mood INTEGER,
  energy INTEGER,
  stress INTEGER,
  sleepiness INTEGER,
  sleep_hours REAL,
  caffeine_mg REAL,
  body_weight REAL,
  focus_domain TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  location TEXT,
  custom_json TEXT,
  metadata_path TEXT NOT NULL,
  media_path TEXT,
  transcript_path TEXT,
  media_exists INTEGER NOT NULL DEFAULT 0,
  transcript_exists INTEGER NOT NULL DEFAULT 0,
  has_media INTEGER NOT NULL DEFAULT 0,
  has_transcript INTEGER NOT NULL DEFAULT 0,
  transcript_language TEXT,
  segment_count INTEGER,
  text_preview TEXT,
  full_text TEXT,
  indexed_at TEXT NOT NULL,
  source_mtime_ms INTEGER,
  source_size_bytes INTEGER,
  index_status TEXT NOT NULL,
  index_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_recordings_date_local ON recordings(date_local);
CREATE INDEX IF NOT EXISTS idx_recordings_timestamp_utc ON recordings(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_recordings_metadata_quality ON recordings(metadata_quality);
CREATE INDEX IF NOT EXISTS idx_recordings_has_transcript ON recordings(has_transcript);
CREATE INDEX IF NOT EXISTS idx_recordings_index_status ON recordings(index_status);

CREATE VIRTUAL TABLE IF NOT EXISTS recordings_fts USING fts5(
  id UNINDEXED,
  full_text,
  text_preview,
  content=''
);
