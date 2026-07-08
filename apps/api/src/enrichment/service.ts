import { spawn } from "node:child_process";
import type { DatabaseSync as Database } from "node:sqlite";
import type { AppConfig } from "../config.js";
import { refreshIndex } from "../indexer/scanVlog.js";

type EnrichProcessResult = {
  stdout: string;
  stderr: string;
  code: number | null;
};

type EnrichmentJsonEnvelope = {
  ok?: unknown;
  message?: unknown;
  field?: unknown;
  field_errors?: unknown;
  [key: string]: unknown;
};

export class EnrichmentValidationError extends Error {
  field: string | null;
  details: EnrichmentJsonEnvelope;

  constructor(
    message: string,
    field: string | null = null,
    details: EnrichmentJsonEnvelope = {},
  ) {
    super(message);
    this.name = "EnrichmentValidationError";
    this.field = field;
    this.details = details;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseJsonObject(output: string): EnrichmentJsonEnvelope | null {
  try {
    const parsed = JSON.parse(output.trim()) as unknown;
    return isRecord(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function firstFieldError(details: EnrichmentJsonEnvelope): string | null {
  if (typeof details.field === "string") return details.field;
  if (isRecord(details.field_errors)) {
    const first = Object.keys(details.field_errors)[0];
    return first || null;
  }
  return null;
}

function errorMessage(details: EnrichmentJsonEnvelope, fallback: string): string {
  if (typeof details.message === "string" && details.message.length > 0) {
    return details.message;
  }
  if (typeof details.error === "string" && details.error.length > 0) {
    return details.error;
  }
  return fallback;
}

function parseValidationError(output: string): EnrichmentValidationError {
  const parsed = parseJsonObject(output);
  if (parsed) {
    return new EnrichmentValidationError(
      errorMessage(parsed, "validation failed"),
      firstFieldError(parsed),
      parsed,
    );
  }
  return new EnrichmentValidationError(output.trim() || "validation failed");
}

function runEnrich(
  config: AppConfig,
  args: string[],
  input?: unknown,
): Promise<EnrichProcessResult> {
  const [command, ...baseArgs] = config.enrichCommand;
  const child = spawn(command, [...baseArgs, ...args], {
    cwd: config.repoRoot,
    env: process.env,
  });

  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk: Buffer) => {
    stdout += chunk.toString();
  });
  child.stderr.on("data", (chunk: Buffer) => {
    stderr += chunk.toString();
  });

  if (input !== undefined) {
    child.stdin.end(`${JSON.stringify(input)}\n`);
  } else {
    child.stdin.end();
  }

  return new Promise((resolve, reject) => {
    child.on("error", reject);
    child.on("exit", (code) => {
      resolve({ stdout, stderr, code });
    });
  });
}

export async function describeEnrichment(config: AppConfig, id: string) {
  const result = await runEnrich(config, ["--describe", id]);
  if (result.code !== 0) {
    throw parseValidationError(result.stdout || result.stderr || `enrich.py exited with code ${result.code}`);
  }
  return JSON.parse(result.stdout) as unknown;
}

export async function submitEnrichment(
  db: Database,
  config: AppConfig,
  id: string,
  payload: unknown,
) {
  const result = await runEnrich(config, ["--json", id], payload);
  const parsed = parseJsonObject(result.stdout);
  if (result.code !== 0) {
    throw parsed
      ? new EnrichmentValidationError(
          errorMessage(parsed, "validation failed"),
          firstFieldError(parsed),
          parsed,
        )
      : parseValidationError(result.stderr || `enrich.py exited with code ${result.code}`);
  }
  if (parsed?.ok === false) {
    throw new EnrichmentValidationError(
      errorMessage(parsed, "validation failed"),
      firstFieldError(parsed),
      parsed,
    );
  }
  const response = parsed ?? (JSON.parse(result.stdout) as unknown);
  return {
    result: response,
    refresh: refreshIndex(db, config),
  };
}
