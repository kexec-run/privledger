import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import net from "node:net";
import { execFileSync, spawn } from "node:child_process";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  buildTestEnvironment,
  cleanupWorkspace,
  createWorkspace,
  retainFailureWorkspace,
} from "../e2e/run-e2e.mjs";

test("workspace has only isolated test data and cleanup preserves neighboring sentinels", () => {
  const workspace = createWorkspace();
  const sentinelDirectory = fs.mkdtempSync(path.join(os.tmpdir(), "privledger-sentinel-"));
  const sibling = path.join(sentinelDirectory, "keep.txt");
  fs.writeFileSync(sibling, "leave untouched");
  try {
    assert.deepEqual(fs.readdirSync(path.join(workspace.root, "vlog")), []);
    assert.equal(fs.existsSync(path.join(workspace.root, "config", "env")), true);
    assert.equal(fs.existsSync(path.join(workspace.root, "docs", "questions.md")), true);
    assert.equal(fs.existsSync(path.join(workspace.root, ".privledger", "privledger-index.sqlite")), false);
    cleanupWorkspace(workspace);
    assert.equal(fs.existsSync(workspace.root), false);
    assert.equal(fs.readFileSync(sibling, "utf8"), "leave untouched");
  } finally {
    fs.rmSync(workspace.root, { recursive: true, force: true });
    fs.rmSync(sentinelDirectory, { recursive: true, force: true });
  }
});

test("inherited data and command overrides are replaced with workspace paths", () => {
  const workspace = createWorkspace();
  try {
    const env = buildTestEnvironment(workspace.root, false, {
      PRIVLEDGER_ROOT: "/personal/data",
      PRIVLEDGER_INDEX_DB: "/personal/index.sqlite",
      PRIVLEDGER_RECORD_COMMAND: "dangerous-recorder",
      PRIVLEDGER_ENRICH_COMMAND: "dangerous-enrich",
      PRIVLEDGER_TRANSCRIBE_COMMAND: "dangerous-transcribe",
    });
    assert.equal(env.PRIVLEDGER_ROOT, workspace.root);
    assert.equal(env.PRIVLEDGER_INDEX_DB, path.join(workspace.root, ".privledger", "privledger-index.sqlite"));
    assert.match(env.PRIVLEDGER_RECORD_COMMAND, /fake-recorder\.mjs$/);
    assert.equal(env.PRIVLEDGER_ENRICH_COMMAND, `python3 ${path.join(workspace.root, "scripts", "enrich.py")}`);
    assert.equal(env.PRIVLEDGER_TRANSCRIBE_COMMAND, `python3 ${path.join(workspace.root, "scripts", "transcript_batch.py")} transcribe --apply`);
  } finally {
    cleanupWorkspace(workspace);
  }
});

test("failed-run retention copies only the owned workspace", () => {
  const workspace = createWorkspace();
  const output = fs.mkdtempSync(path.join(os.tmpdir(), "privledger-e2e-retained-"));
  try {
    fs.writeFileSync(path.join(workspace.root, "vlog", "failure.marker"), "diagnostic");
    const retained = retainFailureWorkspace(workspace, output);
    assert.equal(fs.readFileSync(path.join(retained, "vlog", "failure.marker"), "utf8"), "diagnostic");
    cleanupWorkspace(workspace);
    assert.equal(fs.existsSync(path.join(retained, "vlog", "failure.marker")), true);
  } finally {
    fs.rmSync(workspace.root, { recursive: true, force: true });
    fs.rmSync(output, { recursive: true, force: true });
  }
});


const webDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function responds(url) {
  try {
    return (await fetch(url, { signal: AbortSignal.timeout(500) })).ok;
  } catch {
    return false;
  }
}

function descendantProcessGroups(pid) {
  const rows = execFileSync("ps", ["-axo", "pid=,ppid=,pgid="], { encoding: "utf8" })
    .trim().split("\n").map((row) => row.trim().split(/\s+/).map(Number));
  const descendants = new Set([pid]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const [child, parent] of rows) {
      if (descendants.has(parent) && !descendants.has(child)) {
        descendants.add(child);
        changed = true;
      }
    }
  }
  return new Set(rows.filter(([child]) => descendants.has(child)).map(([, , group]) => group));
}

for (const [signal, activeRecording] of [["SIGINT", false], ["SIGTERM", true]]) {
  test(`${signal}${activeRecording ? " during recording" : ""} awaits teardown before removing the isolated workspace`, {
    skip: process.platform === "win32",
    timeout: 45_000,
  }, async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "privledger-launcher-test-"));
    const sentinel = path.join(directory, "keep.txt");
    fs.writeFileSync(sentinel, "leave untouched");
    const probes = [net.createServer(), net.createServer()];
    await Promise.all(probes.map((server) => new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(0, "127.0.0.1", resolve);
    })));
    const [apiPort, webPort] = probes.map((server) => server.address().port);
    await Promise.all(probes.map((server) => new Promise((resolve) => server.close(resolve))));
    const apiUrl = `http://127.0.0.1:${apiPort}/api/health`;
    const webUrl = `http://127.0.0.1:${webPort}/`;
    const child = spawn(process.execPath, [
      "e2e/run-e2e.mjs", "fake", "--repeat-each=100",
      "--grep", activeRecording
        ? "fake recorder starts from dialog"
        : "record button opens prepare mode without starting recorder",
    ], {
      cwd: webDir,
      env: {
        ...process.env,
        TMPDIR: directory,
        PRIVLEDGER_E2E_API_PORT: String(apiPort),
        PRIVLEDGER_E2E_WEB_PORT: String(webPort),
      },
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let output = "";
    child.stdout.on("data", (data) => { output += data; });
    child.stderr.on("data", (data) => { output += data; });
    const closed = once(child, "close");
    let groups = new Set([child.pid]);
    try {
      let ready = false;
      for (let attempt = 0; attempt < 150; attempt += 1) {
        if (await responds(apiUrl) && await responds(webUrl)) {
          ready = true;
          break;
        }
        assert.equal(child.exitCode, null, output);
        await delay(100);
      }
      assert.equal(ready, true, `Test services did not become ready:\n${output}`);
      const roots = fs.readdirSync(directory).filter((name) => name.startsWith("privledger-e2e-"));
      assert.equal(roots.length, 1);
      let recorderPid;
      if (activeRecording) {
        for (let attempt = 0; attempt < 1000; attempt += 1) {
          const response = await fetch(`http://127.0.0.1:${apiPort}/api/status`, {
            signal: AbortSignal.timeout(500),
          });
          const { recorder } = await response.json();
          if (recorder.state === "recording" && recorder.recentLogs.includes("fake-recorder: ready")) {
            recorderPid = recorder.pid;
            break;
          }
          assert.equal(child.exitCode, null, output);
          await delay(10);
        }
        assert.ok(recorderPid, `No active fake recorder observed:\n${output}`);
      }
      groups = descendantProcessGroups(child.pid);
      child.kill(signal);
      const [code] = await Promise.race([
        closed,
        once(AbortSignal.timeout(20_000), "abort").then(() => {
          throw new Error(`Launcher did not finish ${signal} teardown:\n${output}`);
        }),
      ]);
      assert.equal(code, 1, output);
      assert.equal(await responds(apiUrl), false, "API still responds after launcher exit");
      assert.equal(await responds(webUrl), false, "Web server still responds after launcher exit");
      if (recorderPid) {
        assert.throws(() => process.kill(recorderPid, 0), { code: "ESRCH" }, "Recorder outlived teardown");
      }
      assert.equal(fs.existsSync(path.join(directory, roots[0])), false);
      assert.equal(fs.readFileSync(sentinel, "utf8"), "leave untouched");
    } finally {
      // Also clean up a regressed run whose detached servers outlive the launcher.
      for (const group of groups) {
        try { process.kill(-group, "SIGKILL"); } catch (error) {
          if (error.code !== "ESRCH") throw error;
        }
      }
      await closed;
      fs.rmSync(directory, { recursive: true, force: true });
    }
  });
}
