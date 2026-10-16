import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoot = path.resolve(webDir, "../..");
const failureOutput = path.join(webDir, "test-results", "real-recorder-failures");

export function createWorkspace({ root = sourceRoot, realRecorder = false } = {}) {
  const workspaceRoot = fs.mkdtempSync(path.join(os.tmpdir(), "privledger-e2e-"));
  try {
    for (const directory of ["metadata", "schemas", "scripts"]) {
      fs.cpSync(path.join(root, directory), path.join(workspaceRoot, directory), {
        recursive: true,
        filter: (source) => !source.includes(`${path.sep}.git${path.sep}`),
      });
    }
    fs.mkdirSync(path.join(workspaceRoot, "config"), { recursive: true });
    for (const file of ["custom_schema.yaml", "tags.txt"]) {
      const source = path.join(root, "config", file);
      if (fs.existsSync(source)) fs.copyFileSync(source, path.join(workspaceRoot, "config", file));
    }
    const envSource = realRecorder
      ? path.join(root, "config", "env")
      : path.join(root, "config", "env.sample");
    if (!fs.existsSync(envSource)) {
      throw new Error(`Required test configuration is missing: ${envSource}`);
    }
    fs.copyFileSync(envSource, path.join(workspaceRoot, "config", "env"));
    fs.copyFileSync(
      path.join(root, "schema_validation.py"),
      path.join(workspaceRoot, "schema_validation.py"),
    );
    fs.mkdirSync(path.join(workspaceRoot, "docs"), { recursive: true });
    fs.copyFileSync(
      path.join(root, "docs", "questions.md"),
      path.join(workspaceRoot, "docs", "questions.md"),
    );
    for (const directory of ["vlog", "logs", ".privledger"]) {
      fs.mkdirSync(path.join(workspaceRoot, directory), { recursive: true });
    }
    return { root: workspaceRoot, realRecorder };
  } catch (error) {
    fs.rmSync(workspaceRoot, { recursive: true, force: true });
    throw error;
  }
}

export function buildTestEnvironment(workspaceRoot, realRecorder, inherited = process.env) {
  const root = path.resolve(workspaceRoot);
  const python = process.env.PRIVLEDGER_E2E_PYTHON ?? "python3";
  const fakeRecorder = path.join(webDir, "e2e", "fixtures", "fake-recorder.mjs");
  const env = {
    ...inherited,
    PRIVLEDGER_E2E_ROOT: root,
    PRIVLEDGER_ROOT: root,
    PRIVLEDGER_INDEX_DB: path.join(root, ".privledger", "privledger-index.sqlite"),
    PRIVLEDGER_RECORD_COMMAND: realRecorder
      ? `${python} ${path.join(root, "scripts", "privledger.py")}`
      : `${process.execPath} ${fakeRecorder}`,
    PRIVLEDGER_ENRICH_COMMAND: `${python} ${path.join(root, "scripts", "enrich.py")}`,
    PRIVLEDGER_TRANSCRIBE_COMMAND: `${python} ${path.join(root, "scripts", "transcript_batch.py")} transcribe --apply`,
    PRIVLEDGER_THUMBNAIL_COMMAND: "ffmpeg",
    PRIVLEDGER_FFPROBE_COMMAND: "ffprobe",
    PYTHONPATH: [root, inherited.PYTHONPATH].filter(Boolean).join(path.delimiter),
  };
  if (realRecorder) {
    const cameraBinary = path.join(sourceRoot, "tools", "avcam-cli", ".build", "release", "avcam-cli");
    if (fs.existsSync(cameraBinary)) env.AVCAM_CLI = cameraBinary;
  }
  return env;
}

export function retainFailureWorkspace(workspace, outputDirectory = failureOutput) {
  const destination = path.join(outputDirectory, path.basename(workspace.root));
  fs.mkdirSync(outputDirectory, { recursive: true });
  fs.cpSync(workspace.root, destination, { recursive: true, errorOnExist: true });
  return destination;
}

export function cleanupWorkspace(workspace) {
  const root = path.resolve(workspace.root);
  if (
    path.dirname(root) !== path.resolve(os.tmpdir()) ||
    !path.basename(root).startsWith("privledger-e2e-")
  ) {
    throw new Error(`Refusing to remove a path not created by the E2E launcher: ${root}`);
  }
  fs.rmSync(root, { recursive: true, force: true });
}

function runPlaywright(args, env) {
  const cli = path.join(webDir, "node_modules", "playwright", "cli.js");
  const baseArgs = env.PRIVLEDGER_E2E_REAL_RECORDER === "1"
    ? ["e2e/recording-real.spec.ts"]
    : ["--grep-invert", "@real-recorder"];
  const child = spawn(process.execPath, [cli, "test", ...baseArgs, ...args], {
    cwd: webDir,
    env,
    stdio: "inherit",
    detached: process.platform !== "win32",
  });

  let interrupted = false;
  let killTimer;
  const interrupt = (signal) => {
    if (!child.pid || interrupted) return;
    interrupted = true;
    try {
      if (process.platform !== "win32") process.kill(-child.pid, signal);
      else child.kill(signal);
    } catch {}
    killTimer = setTimeout(() => {
      try {
        if (process.platform !== "win32") process.kill(-child.pid, "SIGKILL");
        else child.kill("SIGKILL");
      } catch {}
    }, 10_000);
  };
  const onInt = () => interrupt("SIGINT");
  const onTerm = () => interrupt("SIGTERM");
  process.on("SIGINT", onInt);
  process.on("SIGTERM", onTerm);

  return new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("close", (code, signal) => {
      clearTimeout(killTimer);
      process.off("SIGINT", onInt);
      process.off("SIGTERM", onTerm);
      resolve(interrupted ? 1 : code ?? (signal ? 1 : 0));
    });
  });
}

async function main() {
  const [mode, ...args] = process.argv.slice(2);
  if (mode !== "fake" && mode !== "real") {
    throw new Error("Usage: node e2e/run-e2e.mjs <fake|real> [Playwright arguments]");
  }
  const realRecorder = mode === "real";
  const workspace = createWorkspace({ realRecorder });
  let exitCode = 1;
  try {
    const env = buildTestEnvironment(workspace.root, realRecorder, {
      ...process.env,
      PRIVLEDGER_E2E_REAL_RECORDER: realRecorder ? "1" : "0",
    });
    exitCode = await runPlaywright(args, env);
  } catch (error) {
    console.error(error);
    exitCode = 1;
  } finally {
    if (realRecorder && exitCode !== 0) {
      try {
        const retained = retainFailureWorkspace(workspace);
        console.error(`Real-recorder failure workspace retained at ${retained}`);
      } catch (error) {
        console.error("Could not preserve the failed real-recorder workspace:", error);
      }
    }
    cleanupWorkspace(workspace);
  }
  process.exitCode = exitCode;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
