import fs from "node:fs";
import path from "node:path";
import Fastify from "fastify";
import type { AppConfig } from "./config.js";
import { createConfig } from "./config.js";
import type { Database } from "./db/connection.js";
import { openDatabase } from "./db/connection.js";
import { refreshIndex } from "./indexer/scanVlog.js";
import { getCalendarMonth } from "./calendar/service.js";
import {
  describeEnrichment,
  submitEnrichment,
} from "./enrichment/service.js";
import {
  getFacets,
  getRecording,
  listRecordings,
  readJsonFile,
  type RecordingFilters,
} from "./recordings/repository.js";
import {
  toRecordingFull,
  toRecordingSummary,
  type RecordingRow,
} from "./recordings/dto.js";
import {
  getRecorderStatus,
  startRecording,
  stopRecording,
} from "./recordings/recorderProcess.js";
import { ensureThumbnail, getMediaInfo } from "./recordings/thumbnails.js";
import { transcribeMissing } from "./transcripts/service.js";

type RecordingGuideSection = {
  title: string;
  prompts: string[];
};

function parseBoolean(value: unknown): boolean | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (value === "true" || value === "1" || value === true) {
    return true;
  }
  if (value === "false" || value === "0" || value === false) {
    return false;
  }
  throw new Error("has_transcript must be true or false");
}

function requireDate(value: string | undefined, name: string): string | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    throw new Error(`${name} must be YYYY-MM-DD`);
  }
  return value;
}

function requireQuality(value: string | undefined): string | undefined {
  if (
    value !== undefined &&
    !["basic", "full", "corrected", "bad"].includes(value)
  ) {
    throw new Error("metadata_quality must be basic, full, corrected, or bad");
  }
  return value;
}

function parseLimit(value: string | undefined): number {
  if (value === undefined) {
    return 50;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 200) {
    throw new Error("limit must be an integer from 1 to 200");
  }
  return parsed;
}

function parseOffset(value: string | undefined): number {
  if (value === undefined) {
    return 0;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error("offset must be a non-negative integer");
  }
  return parsed;
}

function badRequest(reply: { code: (statusCode: number) => { send: (body: unknown) => unknown } }, error: unknown) {
  const details =
    error instanceof Error &&
    "details" in error &&
    typeof error.details === "object" &&
    error.details !== null &&
    !Array.isArray(error.details)
      ? (error.details as Record<string, unknown>)
      : {};
  const body: Record<string, unknown> = {
    ...details,
    error: error instanceof Error ? error.message : String(error),
  };
  if (
    error instanceof Error &&
    "field" in error &&
    (typeof error.field === "string" || error.field === null)
  ) {
    body.field = error.field;
  }
  return reply.code(400).send(body);
}

function parseRecordingGuide(markdown: string): RecordingGuideSection[] {
  const sections: RecordingGuideSection[] = [];
  let current: RecordingGuideSection | null = null;

  for (const line of markdown.split(/\r?\n/)) {
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      current = { title: heading[1].trim(), prompts: [] };
      sections.push(current);
      continue;
    }

    const prompt = line.match(/^\s*(?:[-*]|\d+\.)\s+(.+)$/);
    if (current && prompt) {
      const text = prompt[1].replace(/\*\*/g, "").trim();
      if (text) {
        current.prompts.push(text);
      }
    }
  }

  return sections.filter((section) => section.prompts.length > 0);
}

function readRecordingGuide(config: AppConfig) {
  const guidePath = path.join(config.repoRoot, "docs", "questions.md");
  if (!fs.existsSync(guidePath)) {
    return { source: "docs/questions.md", sections: [] };
  }

  return {
    source: "docs/questions.md",
    sections: parseRecordingGuide(fs.readFileSync(guidePath, "utf8")),
  };
}

export function buildApp(options: { config?: AppConfig; db?: Database } = {}) {
  const config = options.config ?? createConfig();
  const db = options.db ?? openDatabase(config.dbPath);
  refreshIndex(db, config);
  const app = Fastify({ logger: true });

  app.get("/api/health", async () => ({ ok: true }));

  app.get("/api/status", async () => ({
    recorder: getRecorderStatus(),
    dbPath: config.dbPath,
    vlogDir: config.vlogDir,
  }));

  app.get("/api/recording-guide", async () => readRecordingGuide(config));

  app.post("/api/index/refresh", async () => refreshIndex(db, config));

  app.get("/api/recordings", async (request, reply) => {
    const query = request.query as Record<string, string | undefined>;
    try {
      const filters: RecordingFilters = {
        date: requireDate(query.date, "date"),
        from: requireDate(query.from, "from"),
        to: requireDate(query.to, "to"),
        metadata_quality: requireQuality(query.metadata_quality),
        has_transcript: parseBoolean(query.has_transcript),
        tag: query.tag,
        q: query.q,
        limit: parseLimit(query.limit),
        offset: parseOffset(query.offset),
      };
      const rows = listRecordings(db, filters) as RecordingRow[];
      return {
        recordings: rows.map(toRecordingSummary),
        pagination: {
          limit: filters.limit,
          offset: filters.offset,
          count: rows.length,
        },
      };
    } catch (error) {
      return badRequest(reply, error);
    }
  });

  app.get("/api/recordings/:id", async (request, reply) => {
    const { id } = request.params as { id: string };
    const row = getRecording(db, id) as RecordingRow | null;
    if (!row) {
      return reply.code(404).send({ error: "recording not found" });
    }
    return toRecordingFull(row);
  });

  app.get("/api/recordings/:id/full", async (request, reply) => {
    const { id } = request.params as { id: string };
    const row = getRecording(db, id) as RecordingRow | null;
    if (!row) {
      return reply.code(404).send({ error: "recording not found" });
    }
    return toRecordingFull(row);
  });

  app.get("/api/recordings/:id/metadata", async (request, reply) => {
    const { id } = request.params as { id: string };
    const row = getRecording(db, id) as { metadata_path?: string } | null;
    if (!row) {
      return reply.code(404).send({ error: "recording not found" });
    }
    const payload = readJsonFile(row.metadata_path ?? null);
    if (!payload) {
      return reply.code(404).send({ error: "metadata not found" });
    }
    return payload;
  });

  app.get("/api/recordings/:id/transcript", async (request, reply) => {
    const { id } = request.params as { id: string };
    const row = getRecording(db, id) as {
      transcript_path?: string;
      transcript_language?: string;
      segment_count?: number;
      text_preview?: string;
    } | null;
    if (!row) {
      return reply.code(404).send({ error: "recording not found" });
    }
    const payload = readJsonFile(row.transcript_path ?? null);
    if (!payload) {
      return reply.code(404).send({ error: "transcript not found" });
    }
    return {
      summary: {
        language: row.transcript_language ?? null,
        segment_count: row.segment_count ?? null,
        text_preview: row.text_preview ?? null,
      },
      transcript: payload,
    };
  });

  app.get("/api/recordings/:id/media", async (request, reply) => {
    const { id } = request.params as { id: string };
    const row = getRecording(db, id) as { media_path?: string } | null;
    if (!row?.media_path || !fs.existsSync(row.media_path)) {
      return reply.code(404).send({ error: "media not found" });
    }
    return reply.send(fs.createReadStream(row.media_path));
  });

  app.get("/api/recordings/:id/thumbnail", async (request, reply) => {
    const { id } = request.params as { id: string };
    const row = getRecording(db, id) as { media_path?: string } | null;
    if (!row?.media_path || !fs.existsSync(row.media_path)) {
      return reply.code(404).send({ error: "media not found" });
    }
    try {
      const thumbnail = await ensureThumbnail(config, id, row.media_path);
      reply.header("Content-Type", "image/jpeg");
      reply.header("Cache-Control", "private, max-age=3600");
      reply.header("X-Privledger-Thumbnail-Cache", thumbnail.cached ? "hit" : "miss");
      return reply.send(fs.createReadStream(thumbnail.path));
    } catch (error) {
      return reply.code(500).send({
        error: error instanceof Error ? error.message : String(error),
      });
    }
  });

  app.get("/api/recordings/:id/media-info", async (request, reply) => {
    const { id } = request.params as { id: string };
    const row = getRecording(db, id) as {
      media_file?: string | null;
      media_path?: string;
    } | null;
    if (!row?.media_path || !fs.existsSync(row.media_path)) {
      return reply.code(404).send({ error: "media not found" });
    }
    try {
      const info = await getMediaInfo(config, id, row.media_path);
      return {
        file: row.media_file ?? null,
        exists: true,
        durationSeconds: info.durationSeconds,
        thumbnailUrl: `/api/recordings/${id}/thumbnail`,
      };
    } catch (error) {
      return reply.code(500).send({
        error: error instanceof Error ? error.message : String(error),
      });
    }
  });

  app.get("/api/calendar", async (request, reply) => {
    const query = request.query as { month?: string };
    if (!query.month || !/^\d{4}-\d{2}$/.test(query.month)) {
      return reply.code(400).send({ error: "month must be YYYY-MM" });
    }
    return { days: getCalendarMonth(db, query.month) };
  });

  app.get("/api/facets", async () => getFacets(db));

  app.post("/api/recordings/start", async (_request, reply) => {
    try {
      return startRecording(config);
    } catch (error) {
      if (error instanceof Error && error.name === "ConflictError") {
        return reply.code(409).send({ error: error.message });
      }
      throw error;
    }
  });

  app.post("/api/recordings/stop", async () => {
    const result = await stopRecording(db, config);
    const exact = result.recordingId
      ? (getRecording(db, result.recordingId) as RecordingRow | null)
      : null;
    const latest = exact
      ? [exact]
      : (listRecordings(db, { limit: 1, offset: 0 }) as RecordingRow[]);
    return {
      ...result,
      latestRecording: latest[0] ? toRecordingSummary(latest[0]) : null,
    };
  });

  app.get("/api/recordings/:id/enrichment", async (request, reply) => {
    const { id } = request.params as { id: string };
    try {
      return await describeEnrichment(config, id);
    } catch (error) {
      return badRequest(reply, error);
    }
  });

  app.post("/api/recordings/:id/enrichment", async (request, reply) => {
    const { id } = request.params as { id: string };
    try {
      return await submitEnrichment(db, config, id, request.body);
    } catch (error) {
      return badRequest(reply, error);
    }
  });

  app.post("/api/transcripts/transcribe-missing", async () =>
    transcribeMissing(db, config),
  );

  app.addHook("onClose", async () => {
    db.close();
  });

  return app;
}
