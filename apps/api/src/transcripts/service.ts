import { spawn } from "node:child_process";
import type { AppConfig } from "../config.js";
import type { Database } from "../db/connection.js";
import { refreshIndex } from "../indexer/scanVlog.js";

export async function transcribeMissing(db: Database, config: AppConfig) {
  const [command, ...args] = config.transcribeCommand;

  const result = await new Promise<{
    code: number | null;
    stdout: string;
    stderr: string;
  }>((resolve) => {
    const proc = spawn(command, args, { cwd: config.repoRoot });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    proc.stdout.on("data", (chunk: Buffer) => stdout.push(chunk));
    proc.stderr.on("data", (chunk: Buffer) => stderr.push(chunk));
    proc.on("exit", (code) =>
      resolve({
        code,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8"),
      }),
    );
  });

  const refresh = refreshIndex(db, config);
  return { ...result, refresh };
}
