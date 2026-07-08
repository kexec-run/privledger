import fs from "node:fs";
import type { TranscriptSummary } from "./types.js";

function compactPreview(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, 500);
}

export function readTranscriptSummary(path: string | null): TranscriptSummary {
  if (!path) {
    return {
      path: null,
      exists: false,
      language: null,
      segmentCount: null,
      textPreview: null,
      fullText: null,
      error: null,
    };
  }
  if (!fs.existsSync(path)) {
    return {
      path,
      exists: false,
      language: null,
      segmentCount: null,
      textPreview: null,
      fullText: null,
      error: null,
    };
  }

  try {
    const payload = JSON.parse(fs.readFileSync(path, "utf8")) as {
      result?: { language?: unknown };
      transcription?: Array<{ text?: unknown }>;
    };
    const segments = Array.isArray(payload.transcription)
      ? payload.transcription
      : [];
    const fullText = segments
      .map((segment) => (typeof segment.text === "string" ? segment.text : ""))
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();

    return {
      path,
      exists: true,
      language:
        typeof payload.result?.language === "string"
          ? payload.result.language
          : null,
      segmentCount: segments.length,
      textPreview: compactPreview(fullText),
      fullText,
      error: null,
    };
  } catch (error) {
    return {
      path,
      exists: true,
      language: null,
      segmentCount: null,
      textPreview: null,
      fullText: null,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}
