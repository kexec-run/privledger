import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { refreshIndex } from "../src/indexer/scanVlog.js";
import { resolveInside, resolveTranscriptPath } from "../src/files/safePath.js";
import {
  baseMetadata,
  createTestContext,
  transcriptPayload,
  writeJson,
} from "./helpers.js";

test("scanner indexes metadata, transcript summary, and existing life fields", () => {
  const { config, db, vlogDir, transcriptDir } = createTestContext();
  fs.writeFileSync(path.join(vlogDir, "2026-06-29-0930.mov"), "");
  writeJson(path.join(vlogDir, "2026-06-29-0930.json"), baseMetadata());
  writeJson(
    path.join(transcriptDir, "2026-06-29-0930.whisper-large-v3-source.json"),
    transcriptPayload(),
  );

  const summary = refreshIndex(db, config);
  assert.deepEqual(summary, { scanned: 1, indexed: 1, invalid: 0 });

  const row = db
    .prepare("SELECT * FROM recordings WHERE id = ?")
    .get("2026-06-29-0930") as Record<string, unknown>;
  assert.equal(row.mood, 3);
  assert.equal(row.energy, 4);
  assert.equal(row.stress, 2);
  assert.equal(row.sleepiness, 1);
  assert.equal(row.sleep_hours, 7.5);
  assert.equal(row.caffeine_mg, 120);
  assert.equal(row.body_weight, 70.2);
  assert.equal(row.focus_domain, "work");
  assert.equal(row.location, "desk");
  assert.equal(row.has_media, 1);
  assert.equal(row.has_transcript, 1);
  assert.equal(row.transcript_language, "en");
  assert.equal(row.segment_count, 1);
  assert.equal(row.index_status, "ok");
});

test("scanner marks missing media and transcript without dropping metadata", () => {
  const { config, db, vlogDir } = createTestContext();
  writeJson(path.join(vlogDir, "2026-06-29-0930.json"), baseMetadata());

  refreshIndex(db, config);

  const row = db
    .prepare("SELECT media_exists, transcript_exists, has_media, has_transcript FROM recordings WHERE id = ?")
    .get("2026-06-29-0930") as Record<string, unknown>;
  assert.equal(row.media_exists, 0);
  assert.equal(row.transcript_exists, 0);
  assert.equal(row.has_media, 0);
  assert.equal(row.has_transcript, 0);
});

test("invalid metadata becomes an invalid index row", () => {
  const { config, db, vlogDir } = createTestContext();
  fs.writeFileSync(path.join(vlogDir, "broken.json"), "{bad");

  const summary = refreshIndex(db, config);
  assert.equal(summary.invalid, 1);

  const row = db
    .prepare("SELECT index_status, index_error FROM recordings WHERE id = ?")
    .get("broken") as Record<string, unknown>;
  assert.equal(row.index_status, "invalid");
  assert.match(String(row.index_error), /JSON/);
});

test("safe path helpers reject traversal and absolute paths", () => {
  const { vlogDir, transcriptDir } = createTestContext();
  assert.equal(resolveInside(vlogDir, "../outside.mov"), null);
  assert.equal(resolveInside(vlogDir, "/tmp/outside.mov"), null);
  assert.equal(
    resolveTranscriptPath(vlogDir, transcriptDir, "2026-06-29-0930.mov"),
    null,
  );
  assert.ok(
    resolveTranscriptPath(
      vlogDir,
      transcriptDir,
      "transcripts/2026-06-29-0930.whisper-large-v3-source.json",
    ),
  );
});
