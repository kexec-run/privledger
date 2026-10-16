import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  Database,
  Eye,
  EyeOff,
  FileJson,
  RefreshCw,
  Search,
  ShieldCheck,
  Square,
  Tag,
  Video,
  X,
} from "lucide-react";
import { ApiError, jsonFetch } from "./apiClient";
import { LifeMetadata } from "./components/LifeMetadata";
import {
  compactDate,
  durationLabel,
  formatLocalDate,
  localTime,
  numberOrDash,
  timerLabel,
} from "./formatters";
import type {
  CalendarDay,
  EnrichmentDescription,
  EnrichmentForm,
  Facets,
  MediaInfo,
  Recording,
  RecordingGuide,
  Status,
  StopResponse,
} from "./types";

const fallbackDate = formatLocalDate(new Date());

function formFromDescription(description: EnrichmentDescription): EnrichmentForm {
  return {
    ...description.values,
    custom: Object.fromEntries(
      description.custom.fields.map((field) => [field.name, field.value]),
    ),
  };
}

function inferEnrichmentField(message: string): keyof EnrichmentDescription["values"] | "custom" | null {
  const lower = message.toLowerCase();
  const fields: Array<keyof EnrichmentDescription["values"] | "custom"> = [
    "mood",
    "energy",
    "stress",
    "sleepiness",
    "sleep_hours",
    "caffeine_mg",
    "body_weight",
    "focus_domain",
    "tags",
    "location",
    "custom",
  ];
  return fields.find((field) => lower.includes(field)) ?? null;
}

function buildMonthCells(month: string) {
  const [year, monthValue] = month.split("-").map(Number);
  const first = new Date(year, monthValue - 1, 1);
  const startOffset = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - startOffset);

  return Array.from({ length: 35 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    const iso = formatLocalDate(date);
    return {
      iso,
      day: date.getDate(),
      currentMonth: iso.startsWith(month),
    };
  });
}

function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [calendar, setCalendar] = useState<CalendarDay[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [selectedDate, setSelectedDate] = useState(fallbackDate);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sortAscending, setSortAscending] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [screenshotMode, setScreenshotMode] = useState(false);
  const [metadataOpen, setMetadataOpen] = useState(false);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [metadata, setMetadata] = useState<unknown>(null);
  const [mediaInfo, setMediaInfo] = useState<MediaInfo | null>(null);
  const [recordingGuide, setRecordingGuide] = useState<RecordingGuide | null>(null);
  const [selectedGuideTitle, setSelectedGuideTitle] = useState<string | null>(null);
  const [sessionPhase, setSessionPhase] = useState<
    "prepare" | "recording" | "saving" | "enrichment" | null
  >(null);
  const [timerNow, setTimerNow] = useState(() => Date.now());
  const [enrichmentOpen, setEnrichmentOpen] = useState(false);
  const [enrichment, setEnrichment] = useState<EnrichmentDescription | null>(null);
  const [enrichmentForm, setEnrichmentForm] = useState<EnrichmentForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enrichmentError, setEnrichmentError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const dayMap = useMemo(
    () => new Map(calendar.map((day) => [day.date_local, day])),
    [calendar],
  );

  const selectedDay = dayMap.get(selectedDate) ?? null;
  const sortedRecordings = useMemo(
    () =>
      [...recordings].sort((left, right) => {
        const leftTime = new Date(left.startedAt.utc ?? left.startedAt.local ?? 0).getTime();
        const rightTime = new Date(right.startedAt.utc ?? right.startedAt.local ?? 0).getTime();
        return sortAscending ? leftTime - rightTime : rightTime - leftTime;
      }),
    [recordings, sortAscending],
  );
  const selectedRecording =
    recordings.find((recording) => recording.id === selectedId) ??
    sortedRecordings[0] ??
    null;

  const selectedMonth = selectedDate.slice(0, 7);
  const monthLabel = new Date(`${selectedMonth}-01T00:00:00`).toLocaleDateString(
    "en-US",
    { month: "long", year: "numeric" },
  );
  const tags = facets?.tags ?? [];
  const privacyClass = screenshotMode ? "privacy-blur" : "";
  const recorderState = status?.recorder.state ?? "idle";
  const isRecordingActive = recorderState === "recording" || recorderState === "stopping";
  const sessionOpen = sessionPhase !== null || isRecordingActive;
  const activeSessionPhase =
    sessionPhase ?? (isRecordingActive ? "recording" : null);
  const recordingElapsed = timerLabel(status?.recorder.startedAt, timerNow);
  const guideSections = recordingGuide?.sections ?? [];
  const defaultGuide =
    guideSections.find((section) => section.title.toLowerCase() === "opening") ??
    guideSections[0] ??
    null;
  const selectedGuide =
    selectedGuideTitle === ""
      ? null
      : guideSections.find((section) => section.title === selectedGuideTitle) ??
        defaultGuide;
  const enrichmentMetricFields: Array<{
    key: "mood" | "energy" | "stress" | "sleepiness" | "sleep_hours" | "caffeine_mg" | "body_weight";
    label: string;
    min?: number;
    max?: number;
    step?: number;
  }> = [
    { key: "mood", label: "Mood", min: 1, max: 5 },
    { key: "energy", label: "Energy", min: 1, max: 5 },
    { key: "stress", label: "Stress", min: 1, max: 5 },
    { key: "sleepiness", label: "Sleepiness", min: 1, max: 5 },
    { key: "sleep_hours", label: "Sleep hours", min: 0, step: 0.25 },
    { key: "caffeine_mg", label: "Caffeine mg", min: 0 },
    { key: "body_weight", label: "Body weight", min: 0, step: 0.1 },
  ];

  async function loadAll(date = selectedDate, tag: string | null = selectedTag) {
    setError(null);
    const calendarMonth = date.slice(0, 7);
    const [nextStatus, nextCalendar, nextFacets] = await Promise.all([
      jsonFetch<Status>("/api/status"),
      jsonFetch<{ days: CalendarDay[] }>(`/api/calendar?month=${calendarMonth}`),
      jsonFetch<Facets>("/api/facets"),
    ]);

    setStatus(nextStatus);
    setCalendar(nextCalendar.days);
    setFacets(nextFacets);

    const query = new URLSearchParams({ date, limit: "50" });
    if (tag) query.set("tag", tag);
    const nextRecordings = await jsonFetch<{ recordings: Recording[] }>(
      `/api/recordings?${query.toString()}`,
    );
    setRecordings(nextRecordings.recordings);
    setSelectedId((current) => {
      if (current && nextRecordings.recordings.some((item) => item.id === current)) {
        return current;
      }
      return nextRecordings.recordings[0]?.id ?? null;
    });
  }

  useEffect(() => {
    async function initialLoad() {
      void jsonFetch<RecordingGuide>("/api/recording-guide")
        .then(setRecordingGuide)
        .catch(() => setRecordingGuide({ source: "docs/questions.md", sections: [] }));
      await jsonFetch("/api/index/refresh", { method: "POST" });
      await loadAll();
    }

    void initialLoad().catch((caught) => setError(String(caught)));
  }, []);

  useEffect(() => {
    if (status?.recorder.state === "recording") {
      setSessionPhase((current) => current ?? "recording");
    }
  }, [status?.recorder.state]);

  useEffect(() => {
    if (!isRecordingActive) {
      return;
    }
    setTimerNow(Date.now());
    const interval = window.setInterval(() => setTimerNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [isRecordingActive]);

  useEffect(() => {
    if (!selectedRecording) {
      setMetadata(null);
      return;
    }
    if (!metadataOpen) return;
    void jsonFetch<unknown>(`/api/recordings/${selectedRecording.id}/metadata`)
      .then(setMetadata)
      .catch((caught) => setMetadata({ error: String(caught) }));
  }, [selectedRecording, metadataOpen]);

  useEffect(() => {
    if (!selectedRecording?.media.infoUrl) {
      setMediaInfo(null);
      return;
    }
    void jsonFetch<MediaInfo>(selectedRecording.media.infoUrl)
      .then(setMediaInfo)
      .catch(() =>
        setMediaInfo({
          file: selectedRecording.media.file,
          exists: selectedRecording.media.exists,
          durationSeconds: null,
          thumbnailUrl: selectedRecording.media.thumbnailUrl,
        }),
      );
  }, [selectedRecording]);

  useEffect(() => {
    if (!selectedRecording || !enrichmentOpen) {
      return;
    }
    void jsonFetch<EnrichmentDescription>(
      `/api/recordings/${selectedRecording.id}/enrichment`,
    )
      .then((description) => {
        setEnrichment(description);
        setEnrichmentForm(formFromDescription(description));
      })
      .catch((caught) => setError(String(caught)));
  }, [selectedRecording, enrichmentOpen]);

  async function refreshIndex() {
    setBusy(true);
    try {
      await jsonFetch("/api/index/refresh", { method: "POST" });
      await loadAll();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function recordAction(action: "start" | "stop") {
    setBusy(true);
    try {
      if (action === "start") {
        setSessionPhase("recording");
      } else {
        setSessionPhase("saving");
      }
      const result = await jsonFetch<StopResponse | Status["recorder"]>(
        `/api/recordings/${action}`,
        { method: "POST" },
      );
      if (action === "stop" && "latestRecording" in result && result.latestRecording) {
        const nextDate = result.latestRecording.startedAt.dateLocal ?? selectedDate;
        setSelectedTag(null);
        setSelectedDate(nextDate);
        await loadAll(nextDate, null);
        setSelectedId(result.latestRecording.id);
        setEnrichmentOpen(true);
        setSessionPhase("enrichment");
        return;
      }
      await loadAll();
      if (action === "stop") {
        setSessionPhase(null);
      }
    } catch (caught) {
      setError(String(caught));
      if (action === "start") {
        setSessionPhase(null);
      } else {
        setSessionPhase("recording");
      }
    } finally {
      setBusy(false);
    }
  }

  function chooseDate(date: string) {
    setSelectedDate(date);
    setSelectedId(null);
    setInspectorOpen(true);
    void loadAll(date, selectedTag).catch((caught) => setError(String(caught)));
  }


  function changeMonth(delta: number) {
    const next = new Date(`${selectedMonth}-01T00:00:00`);
    next.setMonth(next.getMonth() + delta);
    chooseDate(formatLocalDate(next));
  }
  function chooseTag(tag: string | null) {
    setSelectedTag(tag);
    setSelectedId(null);
    setInspectorOpen(true);
    void loadAll(selectedDate, tag).catch((caught) => setError(String(caught)));
  }

  function clearFieldError(field: string) {
    setFieldErrors((current) => {
      if (!(field in current)) return current;
      const next = { ...current };
      delete next[field];
      return next;
    });
    setEnrichmentError(null);
  }

  function setEnrichmentValue<K extends keyof EnrichmentDescription["values"]>(
    key: K,
    value: EnrichmentDescription["values"][K],
  ) {
    clearFieldError(key);
    setEnrichmentForm((current) => (current ? { ...current, [key]: value } : current));
  }

  function setCustomValue(name: string, value: string | number | boolean | null) {
    clearFieldError("custom");
    setEnrichmentForm((current) =>
      current
        ? { ...current, custom: { ...current.custom, [name]: value } }
        : current,
    );
  }

  function toggleTag(tag: string) {
    clearFieldError("tags");
    setEnrichmentForm((current) => {
      if (!current) return current;
      const tags = current.tags.includes(tag)
        ? current.tags.filter((item) => item !== tag)
        : [...current.tags, tag].sort();
      return { ...current, tags };
    });
  }

  async function submitEnrichment() {
    if (!selectedRecording || !enrichmentForm) return;
    setEnrichmentError(null);
    setFieldErrors({});
    const clientFieldErrors = Object.fromEntries(
      enrichmentMetricFields
        .filter((field) => {
          const value = enrichmentForm[field.key];
          return (
            typeof value === "number" &&
            ((field.min !== undefined && value < field.min) ||
              (field.max !== undefined && value > field.max))
          );
        })
        .map((field) => [
          field.key,
          `${field.label} must be between ${field.min ?? "-∞"} and ${field.max ?? "∞"}.`,
        ]),
    );
    if (Object.keys(clientFieldErrors).length > 0) {
      setFieldErrors(clientFieldErrors);
      setEnrichmentError("Fix invalid enrichment fields.");
      return;
    }
    const { custom: _custom, ...payloadWithoutCustom } = enrichmentForm;
    const payload = enrichment?.custom.enabled ? enrichmentForm : payloadWithoutCustom;
    setBusy(true);
    try {
      await jsonFetch(`/api/recordings/${selectedRecording.id}/enrichment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await loadAll(selectedDate, selectedTag);
      setMetadata(null);
      setEnrichmentOpen(false);
      setSessionPhase(null);
      setEnrichmentError(null);
    } catch (caught) {
      const metricField = enrichmentMetricFields.find((field) => {
        const value = enrichmentForm[field.key];
        return (
          typeof value === "number" &&
          ((field.min !== undefined && value < field.min) ||
            (field.max !== undefined && value > field.max))
        );
      })?.key;
      if (caught instanceof ApiError) {
        setEnrichmentError(caught.message);
        const inferredField = caught.field ?? inferEnrichmentField(caught.message) ?? metricField;
        if (Object.keys(caught.fieldErrors).length > 0) {
          setFieldErrors(caught.fieldErrors);
        } else if (inferredField) {
          setFieldErrors({ [inferredField]: caught.message });
        }
      } else {
        const message = String(caught);
        setEnrichmentError(message);
        if (metricField) {
          setFieldErrors({ [metricField]: message });
        }
      }
    } finally {
      setBusy(false);
    }
  }

  function renderEnrichmentForm(closeLabel = "Close", onClose = () => setEnrichmentOpen(false)) {
    return (
      <div className="enrichment-form" data-testid="enrichment-form">
        {enrichmentForm ? (
          <>
            {enrichmentError ? (
              <div className="enrichment-error">{enrichmentError}</div>
            ) : null}
            <div className="field-grid">
              {enrichmentMetricFields.map((field) => (
                <label
                  key={field.key}
                  className={fieldErrors[field.key] ? "invalid-field" : ""}
                  data-testid={`enrichment-field-${field.key}`}
                >
                  <span>{field.label}</span>
                  <input
                    data-testid={`enrichment-input-${field.key}`}
                    type="number"
                    min={field.min}
                    max={field.max}
                    step={field.step ?? 1}
                    value={enrichmentForm[field.key] ?? ""}
                    onChange={(event) =>
                      setEnrichmentValue(
                        field.key,
                        event.currentTarget.value === ""
                          ? null
                          : Number(event.currentTarget.value),
                      )
                    }
                  />
                  {fieldErrors[field.key] ? (
                    <small>{fieldErrors[field.key]}</small>
                  ) : null}
                </label>
              ))}
            </div>

            <label
              className={`wide-field ${fieldErrors.focus_domain ? "invalid-field" : ""}`}
              data-testid="enrichment-field-focus_domain"
            >
              <span>Focus domain</span>
              <select
                data-testid="enrichment-input-focus_domain"
                value={enrichmentForm.focus_domain ?? ""}
                onChange={(event) =>
                  setEnrichmentValue(
                    "focus_domain",
                    event.currentTarget.value || null,
                  )
                }
              >
                <option value="">None</option>
                {(enrichment?.tag_vocabulary ?? tags).map((tag) => (
                  <option key={tag} value={tag}>
                    {tag}
                  </option>
                ))}
              </select>
              {fieldErrors.focus_domain ? (
                <small>{fieldErrors.focus_domain}</small>
              ) : null}
            </label>

            <div className={`tag-picker ${fieldErrors.tags ? "invalid-field" : ""}`} data-testid="enrichment-tags">
              {(enrichment?.tag_vocabulary ?? tags).map((tag) => (
                <button
                  key={tag}
                  className={enrichmentForm.tags.includes(tag) ? "active" : ""}
                  onClick={() => toggleTag(tag)}
                >
                  {tag}
                </button>
              ))}
              {fieldErrors.tags ? <small>{fieldErrors.tags}</small> : null}
            </div>

            <label className={`wide-field ${fieldErrors.location ? "invalid-field" : ""}`} data-testid="enrichment-field-location">
              <span>Location</span>
              <input
                data-testid="enrichment-input-location"
                value={enrichmentForm.location ?? ""}
                onChange={(event) =>
                  setEnrichmentValue("location", event.currentTarget.value || null)
                }
              />
              {fieldErrors.location ? <small>{fieldErrors.location}</small> : null}
            </label>

            {enrichment?.custom.enabled ? (
              <div className="custom-fields">
                <h4>Custom</h4>
                {enrichment.custom.fields.map((field) => (
                  <label
                    key={field.name}
                    className={fieldErrors.custom ? "invalid-field" : ""}
                  >
                    <span>{field.name}</span>
                    {field.type === "boolean" ? (
                      <input
                        type="checkbox"
                        checked={Boolean(enrichmentForm.custom[field.name])}
                        onChange={(event) =>
                          setCustomValue(field.name, event.currentTarget.checked)
                        }
                      />
                    ) : (
                      <input
                        type={
                          field.type === "integer" || field.type === "number"
                            ? "number"
                            : "text"
                        }
                        step={field.type === "number" ? 0.1 : 1}
                        value={String(enrichmentForm.custom[field.name] ?? "")}
                        onChange={(event) =>
                          setCustomValue(
                            field.name,
                            event.currentTarget.value === ""
                              ? null
                              : field.type === "integer" || field.type === "number"
                                ? Number(event.currentTarget.value)
                                : event.currentTarget.value,
                          )
                        }
                      />
                    )}
                    {fieldErrors.custom ? <small>{fieldErrors.custom}</small> : null}
                  </label>
                ))}
              </div>
            ) : null}

            <div className="enrichment-actions">
              <button className="button neutral" disabled={busy} onClick={onClose}>
                {closeLabel}
              </button>
              <button
                className="button record"
                data-testid="save-enrichment-button"
                disabled={busy}
                onClick={() => void submitEnrichment()}
              >
                Save enrichment
              </button>
            </div>
          </>
        ) : (
          <p className="muted-copy">Loading enrichment fields…</p>
        )}
      </div>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-group">
          <div className="brand-mark">
            <ShieldCheck size={30} />
          </div>
          <h1>Privledger</h1>
          <span className={`status-pill ${status?.recorder.state ?? "idle"}`}>
            <Circle size={10} fill="currentColor" />
            {status?.recorder.state ?? "Idle"}
          </span>
        </div>
        <div className="topbar-actions">
          <button
            className="button record"
            data-testid="record-button"
            disabled={busy || isRecordingActive}
            onClick={() => {
              setSelectedGuideTitle(null);
              setSessionPhase("prepare");
            }}
          >
            <Circle size={16} fill="currentColor" />
            {isRecordingActive ? "Recording" : "Record"}
          </button>
          <button
            className={`button neutral ${screenshotMode ? "active" : ""}`}
            data-testid="screenshot-mode-button"
            onClick={() => setScreenshotMode((current) => !current)}
          >
            {screenshotMode ? <EyeOff size={16} /> : <Eye size={16} />}
            Screenshot mode
          </button>
          <button className="button neutral" data-testid="refresh-index-button" disabled={busy} onClick={refreshIndex}>
            <RefreshCw size={16} /> Refresh Index
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="left-rail">
          <div className="rail-section calendar-section">
            <div className="section-heading">
              <div>
                <span className="eyeless-label">Calendar</span>
                <h2>{monthLabel}</h2>
              </div>
              <div className="small-arrows">
                <button
                  aria-label="Previous month"
                  onClick={() => changeMonth(-1)}
                  type="button"
                >
                  <ChevronLeft size={18} />
                </button>
                <button
                  aria-label="Next month"
                  onClick={() => changeMonth(1)}
                  type="button"
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
            <div className="weekdays">
              {["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"].map((day) => (
                <span key={day}>{day}</span>
              ))}
            </div>
            <div className="calendar-grid">
              {buildMonthCells(selectedMonth).map((cell) => {
                const day = dayMap.get(cell.iso);
                const hasTag = selectedTag ? day?.tags.includes(selectedTag) : Boolean(day);
                return (
                  <button
                    key={cell.iso}
                    className={[
                      "day-cell",
                      cell.currentMonth ? "" : "outside",
                      selectedDate === cell.iso ? "selected" : "",
                      hasTag ? "tagged" : "",
                    ].join(" ")}
                    data-testid={`calendar-day-${cell.iso}`}
                    onClick={() => chooseDate(cell.iso)}
                  >
                    <span>{cell.day}</span>
                    <i>{day?.recording_count ? "•".repeat(Math.min(day.recording_count, 3)) : ""}</i>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="rail-section">
            <div className="section-heading compact">
              <h2>Tags</h2>
              <ChevronDown size={17} />
            </div>
            <div className="tag-list">
              <button
                className={`tag-row ${selectedTag === null ? "active" : ""}`}
                data-testid="tag-row-all"
                onClick={() => chooseTag(null)}
              >
                <Tag size={16} />
                <span>All recordings</span>
                <strong>
                  {calendar.reduce((total, day) => total + day.recording_count, 0)}
                </strong>
              </button>
              {tags.map((tag) => (
                <button
                  key={tag}
                  className={`tag-row ${selectedTag === tag ? "active" : ""}`}
                  data-testid="tag-row"
                  data-tag={tag}
                  onClick={() => chooseTag(tag)}
                >
                  <Tag size={16} />
                  <span>{tag}</span>
                  <strong>{facets?.tagCounts[tag] ?? ""}</strong>
                </button>
              ))}
            </div>
          </div>

          <div className="index-card">
            <div>
              <Database size={20} />
              <span>Index size</span>
              <strong>{calendar.reduce((total, day) => total + day.recording_count, 0)} rec</strong>
            </div>
            <div className="meter">
              <span style={{ width: "68%" }} />
            </div>
            <p>SQLite cache · source of truth remains vlog/</p>
          </div>
        </aside>

        <section className="center-stage">
          <div className="day-header">
            <div>
              <h2>{compactDate(selectedDate)}</h2>
              <span>{recordings.length} {selectedTag ? `matching ${selectedTag}` : "recordings"}</span>
            </div>
            <button
              aria-label={`Sort by start time ${sortAscending ? "descending" : "ascending"}`}
              className="sort-button"
              onClick={() => setSortAscending((current) => !current)}
              type="button"
            >
              Start time {sortAscending ? "↑" : "↓"} <ChevronDown size={16} />
            </button>
          </div>
          {error ? <div className="error-banner">{error}</div> : null}

          <div className="recording-list">
            {recordings.length === 0 ? (
              <div className="empty-state">
                <CalendarDays size={24} />
                <h3>No recordings for this filter</h3>
                <p>Try another day, tag, or refresh the index.</p>
              </div>
            ) : (
              sortedRecordings.map((recording) => (
                <button
                  key={recording.id}
                  className={`recording-card ${
                    inspectorOpen && selectedRecording?.id === recording.id ? "selected" : ""
                  }`}
                  data-recording-id={recording.id}
                  data-testid="recording-card"
                  onClick={() => {
                    setSelectedId(recording.id);
                    setSummaryOpen(false);
                    setInspectorOpen(true);
                    setMetadataOpen(false);
                  }}
                >
                  <span className="video-icon">
                    <Video size={20} />
                  </span>
                  <span className="recording-copy">
                    <strong>{localTime(recording.startedAt.local)} recording</strong>
                    <small>
                      {recording.quality ?? "unknown"} · {recording.media.device ?? "device"} ·{" "}
                      {recording.transcript.exists ? "transcript ready" : "no transcript"}
                    </small>
                  </span>
                  <span className="recording-tags">
                    {recording.life.tags.slice(0, 2).map((tag) => (
                      <i key={tag}>{tag}</i>
                    ))}
                  </span>
                </button>
              ))
            )}
          </div>
          <div className="end-of-day">End of day</div>
        </section>

        <aside className="inspector" data-testid="inspector-panel">
          {selectedRecording && inspectorOpen ? (
            <>
              <div className="inspector-head">
                <div>
                  <h2>{localTime(selectedRecording.startedAt.local)} recording</h2>
                  <span>
                    {selectedRecording.startedAt.dateLocal} · {selectedRecording.quality} ·{" "}
                    {selectedRecording.media.file ?? "no media"}
                  </span>
                </div>
                <button
                  className="icon-button ghost"
                  aria-label="Close inspector"
                  onClick={() => {
                    setInspectorOpen(false);
                    setMetadataOpen(false);
                    setSummaryOpen(false);
                  }}
                >
                  <X size={19} />
                </button>
              </div>

              <section className="inspector-block" data-testid="media-block">
                <h3>Media</h3>
                <div className="media-shell">
                  <div className={`video-preview ${privacyClass}`}>
                    {selectedRecording.media.thumbnailUrl ? (
                      <img
                        src={selectedRecording.media.thumbnailUrl}
                        alt=""
                        aria-hidden="true"
                      />
                    ) : (
                      <Video size={28} />
                    )}
                  </div>
                  <div className="media-details">
                    <strong>
                      {selectedRecording.media.exists ? "Media available" : "Media missing"}
                    </strong>
                    <span>{durationLabel(mediaInfo?.durationSeconds)}</span>
                    <small>{selectedRecording.media.file ?? "No media file"}</small>
                  </div>
                </div>
              </section>

              <LifeMetadata life={selectedRecording.life} />

              <section className="inspector-block enrichment-block" data-testid="enrichment-block">
                <div className="section-heading compact">
                  <h3>Enrichment</h3>
                </div>
                {!enrichmentOpen ? (
                  <button
                    className="button enrich-primary"
                    data-testid="enrich-metadata-button"
                    onClick={() => setEnrichmentOpen(true)}
                  >
                    Enrich metadata
                  </button>
                ) : null}
                {enrichmentOpen ? renderEnrichmentForm() : null}
              </section>

              <section className="inspector-block transcript-block">
                <div className="section-heading compact">
                  <h3>Transcript Summary</h3>
                  <ChevronDown size={17} />
                </div>
                <div className="summary-box">
                  {selectedRecording.transcript.exists ? (
                    <>
                      <div className="summary-row">
                        <strong>00:00-00:45</strong>
                        <span className={privacyClass}>
                          {selectedRecording.transcript.preview ?? "Transcript preview"}
                        </span>
                      </div>
                      {summaryOpen ? (
                        <p className={`raw-text ${privacyClass}`}>
                          Raw transcript remains hidden until requested. The UI can expand this
                          area into timestamped segments once summary windows are available.
                        </p>
                      ) : null}
                      <button className="button subtle" onClick={() => setSummaryOpen(!summaryOpen)}>
                        {summaryOpen ? "Show less" : "Show more"}
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="summary-row muted">
                        <strong>No transcript</strong>
                        <span>Summary windows will appear here after transcription.</span>
                      </div>
                      <button className="button subtle" disabled>
                        Show more
                      </button>
                    </>
                  )}
                </div>
              </section>

              <section className="metadata-row">
                <button className="metadata-toggle" data-testid="metadata-toggle" onClick={() => setMetadataOpen(!metadataOpen)}>
                  <FileJson size={18} /> Metadata <ChevronDown size={16} />
                </button>
                <button className="button neutral" onClick={() => setMetadataOpen(true)}>
                  Open JSON
                </button>
              </section>
              {metadataOpen ? (
                <pre className={`metadata-preview ${privacyClass}`}>
                  {JSON.stringify(metadata ?? { loading: true }, null, 2)}
                </pre>
              ) : null}
            </>
          ) : (
            <div className="inspector-empty">
              <Search size={24} />
              <h2>Select a recording</h2>
              <p>Media, life metadata, transcript summary, and raw JSON will appear here.</p>
            </div>
          )}
        </aside>
      </section>
      {sessionOpen ? (
        <div className="session-overlay" role="presentation">
          <section
            className={`session-dialog ${activeSessionPhase ?? "recording"}`}
            data-testid="session-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="session-title"
          >
            <header className="session-header">
              <div>
                <span className="session-kicker">
                  <Circle size={11} fill="currentColor" />
                  {activeSessionPhase === "enrichment"
                    ? "Recording complete"
                    : activeSessionPhase === "prepare"
                      ? "Prepare"
                      : "Recording"}
                </span>
                <h2 id="session-title">
                  {activeSessionPhase === "enrichment"
                    ? "Enrich metadata"
                    : activeSessionPhase === "saving"
                      ? "Saving recording"
                      : activeSessionPhase === "prepare"
                        ? "Prepare recording"
                        : "Recording"}
                </h2>
              </div>
              <div className="session-controls">
                {activeSessionPhase === "recording" ? (
                  <strong className="session-timer">{recordingElapsed}</strong>
                ) : null}
                {activeSessionPhase === "prepare" ? (
                  <>
                    <button
                      className="button neutral"
                      data-testid="cancel-recording-button"
                      disabled={busy}
                      onClick={() => setSessionPhase(null)}
                    >
                      Cancel
                    </button>
                    <button
                      className="button record session-stop"
                      data-testid="start-recording-button"
                      disabled={busy}
                      onClick={() => void recordAction("start")}
                    >
                      <Circle size={15} fill="currentColor" />
                      Start recording
                    </button>
                  </>
                ) : null}
                {activeSessionPhase === "recording" ? (
                  <button
                    className="button record session-stop"
                    data-testid="stop-recording-button"
                    disabled={busy}
                    onClick={() => void recordAction("stop")}
                  >
                    <Square size={15} fill="currentColor" />
                    Stop recording
                  </button>
                ) : null}
                {activeSessionPhase === "enrichment" ? (
                  <button
                    className="icon-button ghost"
                    aria-label="Close session dialog"
                    onClick={() => setSessionPhase(null)}
                  >
                    <X size={19} />
                  </button>
                ) : null}
              </div>
            </header>

            {activeSessionPhase === "saving" ? (
              <div className="session-saving">
                <RefreshCw size={24} />
                <div>
                  <strong>Saving locally</strong>
                  <span>Stopping recorder, refreshing index, and finding the new JSON.</span>
                </div>
              </div>
            ) : null}

            {activeSessionPhase === "prepare" || activeSessionPhase === "recording" ? (
              <>
                <div className="session-status-line">
                  {activeSessionPhase === "prepare" ? (
                    <>
                      <span>Recorder not started</span>
                      <span>Read prompts, then start when ready</span>
                    </>
                  ) : (
                    <>
                      <span>Saving locally</span>
                      <span>Camera owned by Python recorder</span>
                    </>
                  )}
                </div>

                <section className="guide-panel">
                  <div className="guide-heading">
                    <div>
                      <span className="eyeless-label">{recordingGuide?.source ?? "docs/questions.md"}</span>
                      <h3>questions.md guide</h3>
                    </div>
                    <p>Use these as prompts, not a checklist.</p>
                  </div>

                  {guideSections.length > 0 ? (
                    <div className="guide-section-list">
                      {guideSections.slice(0, 6).map((section) => {
                        const isExpanded = section === selectedGuide;

                        return (
                          <div
                            className={`guide-section ${isExpanded ? "expanded" : ""}`}
                            key={section.title}
                          >
                            <button
                              aria-expanded={isExpanded}
                              className="guide-section-title"
                              data-testid="guide-section-title"
                              data-guide-title={section.title}
                              onClick={() =>
                                setSelectedGuideTitle(isExpanded ? "" : section.title)
                              }
                              type="button"
                            >
                              <span>{section.title}</span>
                              <small>{section.prompts.length} prompts</small>
                              <ChevronDown size={17} />
                            </button>
                            <div
                              aria-hidden={!isExpanded}
                              className={`prompt-region ${isExpanded ? "open" : ""}`}
                              data-testid="prompt-region"
                            >
                              <div className="prompt-list">
                                {section.prompts.slice(0, 5).map((prompt) => (
                                  <div className="prompt-card" key={prompt}>
                                    {prompt}
                                  </div>
                                ))}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="muted-copy">No guide prompts found.</p>
                  )}
                </section>

                {activeSessionPhase === "recording" ? (
                  <div className="quick-metadata-row">
                    <span>Enrichment opens after stop</span>
                    <strong>mood, energy, stress, sleepiness, tags</strong>
                  </div>
                ) : null}
              </>
            ) : null}

            {activeSessionPhase === "enrichment" ? (
              <section className="session-enrichment" data-testid="session-enrichment">
                <p className="muted-copy">
                  Recording saved. Add life metadata now, or close and re-enrich from the
                  inspector later.
                </p>
                {renderEnrichmentForm("Enrich later", () => {
                  setSessionPhase(null);
                  setEnrichmentOpen(false);
                })}
              </section>
            ) : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}

export default App;
