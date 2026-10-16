import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
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
