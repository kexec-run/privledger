export type Recording = {
  id: string;
  startedAt: {
    utc: string | null;
    local: string | null;
    dateLocal: string | null;
  };
  quality: string;
  media: {
    file: string | null;
    device: string | null;
    exists: boolean;
    url: string | null;
    thumbnailUrl: string | null;
    infoUrl: string | null;
  };
  transcript: {
    file: string | null;
    exists: boolean;
    url: string | null;
    preview: string | null;
    segmentCount: number | null;
    language: string | null;
  };
  life: {
    mood: number | null;
    energy: number | null;
    stress: number | null;
    sleepiness: number | null;
    sleepHours: number | null;
    caffeineMg: number | null;
    bodyWeight: number | null;
    focusDomain: string | null;
    tags: string[];
    location: string | null;
    custom: unknown;
  };
};

export type CalendarDay = {
  date_local: string;
  recording_count: number;
  bad_count: number;
  good_count: number;
  transcript_count: number;
  avg_mood: number | null;
  avg_energy: number | null;
  avg_stress: number | null;
  avg_sleepiness: number | null;
  avg_sleep_hours: number | null;
  total_caffeine_mg: number | null;
  tags: string[];
};

export type Facets = {
  tags: string[];
  tagCounts: Record<string, number>;
  focusDomains: string[];
  qualities: string[];
  dateRange: {
    from: string | null;
    to: string | null;
  };
};

export type Status = {
  recorder: {
    state: "idle" | "recording" | "stopping" | "last_error";
    pid: number | null;
    startedAt: string | null;
    lastExitCode: number | null;
    lastError: string | null;
    recentLogs: string[];
  };
};

export type CustomField = {
  name: string;
  type: "integer" | "number" | "boolean" | "string";
  value: string | number | boolean | null;
};

export type EnrichmentDescription = {
  id: string;
  values: {
    mood: number | null;
    energy: number | null;
    stress: number | null;
    sleepiness: number | null;
    sleep_hours: number | null;
    caffeine_mg: number | null;
    body_weight: number | null;
    focus_domain: string | null;
    tags: string[];
    location: string | null;
  };
  tag_vocabulary: string[];
  custom: {
    enabled: boolean;
    schema_hash: string | null;
    fields: CustomField[];
  };
};

export type EnrichmentForm = EnrichmentDescription["values"] & {
  custom: Record<string, string | number | boolean | null>;
};

export type StopResponse = Status["recorder"] & {
  latestRecording?: Recording | null;
};

export type MediaInfo = {
  file: string | null;
  exists: boolean;
  durationSeconds: number | null;
  thumbnailUrl: string | null;
};

export type RecordingGuide = {
  source: string;
  sections: Array<{
    title: string;
    prompts: string[];
  }>;
};
