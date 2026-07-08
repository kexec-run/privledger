import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { AppConfig } from "../config.js";
import type { Database } from "../db/connection.js";
import { refreshIndex } from "../indexer/scanVlog.js";

type RecorderStateName = "idle" | "recording" | "stopping" | "last_error";

type RecorderState = {
  state: RecorderStateName;
  pid: number | null;
  startedAt: string | null;
  lastExitCode: number | null;
  lastError: string | null;
  recentLogs: string[];
};

const state: RecorderState = {
  state: "idle",
  pid: null,
  startedAt: null,
  lastExitCode: null,
  lastError: null,
  recentLogs: [],
};

let proc: ChildProcessWithoutNullStreams | null = null;

function pushLog(chunk: Buffer): void {
  const lines = chunk.toString("utf8").split(/\r?\n/).filter(Boolean);
  state.recentLogs.push(...lines);
  state.recentLogs = state.recentLogs.slice(-100);
}

function latestWrittenRecordingId(): string | null {
  for (const line of [...state.recentLogs].reverse()) {
    const match = line.match(/Metadata written -> ([^.]+)\.json/);
    if (match) return match[1];
  }
  return null;
}

export function getRecorderStatus(): RecorderState {
  return { ...state, recentLogs: [...state.recentLogs] };
}

export function startRecording(config: AppConfig): RecorderState {
  if (proc && proc.exitCode === null) {
    const error = new Error("recording already active");
    error.name = "ConflictError";
    throw error;
  }

  const [command, ...args] = config.recordCommand;
  proc = spawn(command, args, {
    cwd: config.repoRoot,
    env: process.env,
    detached: true,
  });

  state.state = "recording";
  state.pid = proc.pid ?? null;
  state.startedAt = new Date().toISOString();
  state.lastExitCode = null;
  state.lastError = null;
  state.recentLogs = [];

  proc.stdout.on("data", pushLog);
  proc.stderr.on("data", pushLog);
  proc.on("error", (error) => {
    state.state = "last_error";
    state.lastError = error.message;
    state.pid = null;
  });
  proc.on("exit", (code) => {
    const requestedStop = state.state === "stopping";
    state.state = code === 0 || requestedStop ? "idle" : "last_error";
    state.lastExitCode = code;
    state.pid = null;
    if (code !== 0 && !requestedStop) {
      state.lastError = `recorder exited with code ${code}`;
    }
    proc = null;
  });

  return getRecorderStatus();
}

export async function stopRecording(
  db: Database,
  config: AppConfig,
): Promise<RecorderState & { refresh?: ReturnType<typeof refreshIndex>; recordingId?: string | null }> {
  if (!proc || proc.exitCode !== null) {
    return getRecorderStatus();
  }

  state.state = "stopping";
  process.kill(-proc.pid!, "SIGINT");

  await new Promise<void>((resolve) => {
    proc?.once("exit", () => resolve());
  });

  const recordingId = latestWrittenRecordingId();
  const refresh = refreshIndex(db, config);
  return { ...getRecorderStatus(), refresh, recordingId };
}
