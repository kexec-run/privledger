import { fileURLToPath } from "node:url";
import path from "node:path";

export type AppConfig = {
  repoRoot: string;
  vlogDir: string;
  transcriptDir: string;
  dbPath: string;
  thumbnailDir: string;
  recordCommand: string[];
  enrichCommand: string[];
  thumbnailCommand: string[];
  ffprobeCommand: string[];
  transcribeCommand: string[];
  host: string;
  port: number;
};

const here = path.dirname(fileURLToPath(import.meta.url));
const defaultRepoRoot = path.resolve(here, "../../..");

export function createConfig(overrides: Partial<AppConfig> = {}): AppConfig {
  const repoRoot = path.resolve(
    overrides.repoRoot ?? process.env.PRIVLEDGER_ROOT ?? defaultRepoRoot,
  );
  const vlogDir = path.resolve(overrides.vlogDir ?? path.join(repoRoot, "vlog"));
  const recordCommand = withoutInteractiveEnrich(
    overrides.recordCommand ?? splitCommand(process.env.PRIVLEDGER_RECORD_COMMAND) ?? [
      "python3",
      path.join(repoRoot, "scripts", "privledger.py"),
    ],
  );
  const enrichCommand = overrides.enrichCommand ??
    splitCommand(process.env.PRIVLEDGER_ENRICH_COMMAND) ?? [
      "python3",
      path.join(repoRoot, "scripts", "enrich.py"),
    ];
  const thumbnailCommand = overrides.thumbnailCommand ??
    splitCommand(process.env.PRIVLEDGER_THUMBNAIL_COMMAND) ?? ["ffmpeg"];
  const ffprobeCommand = overrides.ffprobeCommand ??
    splitCommand(process.env.PRIVLEDGER_FFPROBE_COMMAND) ?? ["ffprobe"];
  const transcribeCommand = overrides.transcribeCommand ??
    splitCommand(process.env.PRIVLEDGER_TRANSCRIBE_COMMAND) ?? [
      "python3",
      path.join(repoRoot, "scripts", "transcript_batch.py"),
      "transcribe",
      "--apply",
    ];

  return {
    repoRoot,
    vlogDir,
    transcriptDir: path.resolve(
      overrides.transcriptDir ?? path.join(vlogDir, "transcripts"),
    ),
    dbPath: path.resolve(
      overrides.dbPath ??
        process.env.PRIVLEDGER_INDEX_DB ??
        path.join(repoRoot, ".privledger", "privledger-index.sqlite"),
    ),
    thumbnailDir: path.resolve(
      overrides.thumbnailDir ?? path.join(repoRoot, ".privledger", "thumbnails"),
    ),
    recordCommand,
    enrichCommand,
    thumbnailCommand,
    ffprobeCommand,
    transcribeCommand,
    host: overrides.host ?? process.env.PRIVLEDGER_API_HOST ?? "127.0.0.1",
    port: overrides.port ?? Number(process.env.PRIVLEDGER_API_PORT ?? "4577"),
  };
}

function splitCommand(command: string | undefined): string[] | null {
  const parts = command?.trim().split(/\s+/).filter(Boolean) ?? [];
  return parts.length > 0 ? parts : null;
}

function withoutInteractiveEnrich(command: string[]): string[] {
  return command.filter((part) => part !== "--enrich");
}
