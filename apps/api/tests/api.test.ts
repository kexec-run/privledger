import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { buildApp } from "../src/app.js";
import { createConfig } from "../src/config.js";
import { refreshIndex } from "../src/indexer/scanVlog.js";
import {
  baseMetadata,
  createTestContext,
  transcriptPayload,
  writeJson,
} from "./helpers.js";

test("recording and calendar APIs return indexed data", async () => {
  const { config, db, vlogDir, transcriptDir } = createTestContext();
  fs.writeFileSync(path.join(vlogDir, "2026-06-29-0930.mov"), "");
  writeJson(path.join(vlogDir, "2026-06-29-0930.json"), baseMetadata());
  writeJson(
    path.join(transcriptDir, "2026-06-29-0930.whisper-large-v3-source.json"),
    transcriptPayload(),
  );
  refreshIndex(db, config);

  const app = buildApp({ config, db });

  const list = await app.inject({ method: "GET", url: "/api/recordings" });
  assert.equal(list.statusCode, 200);
  assert.equal(list.json().recordings.length, 1);
  assert.equal(list.json().recordings[0].life.sleepHours, 7.5);
  assert.equal(list.json().recordings[0].media.url, "/api/recordings/2026-06-29-0930/media");
  assert.equal(
    list.json().recordings[0].media.thumbnailUrl,
    "/api/recordings/2026-06-29-0930/thumbnail",
  );
  assert.equal(
    list.json().recordings[0].media.infoUrl,
    "/api/recordings/2026-06-29-0930/media-info",
  );
  assert.equal("full_text" in list.json().recordings[0], false);

  const full = await app.inject({
    method: "GET",
    url: "/api/recordings/2026-06-29-0930/full",
  });
  assert.equal(full.statusCode, 200);
  assert.equal(full.json().life.tags[0], "work");

  const metadata = await app.inject({
    method: "GET",
    url: "/api/recordings/2026-06-29-0930/metadata",
  });
  assert.equal(metadata.statusCode, 200);
  assert.equal(metadata.json().sleep_hours, 7.5);

  const calendar = await app.inject({
    method: "GET",
    url: "/api/calendar?month=2026-06",
  });
  assert.equal(calendar.statusCode, 200);
  assert.equal(calendar.json().days[0].recording_count, 1);
  assert.equal(calendar.json().days[0].avg_mood, 3);
  assert.deepEqual(calendar.json().days[0].tags, ["planning", "work"]);

  const facets = await app.inject({ method: "GET", url: "/api/facets" });
  assert.equal(facets.statusCode, 200);
  assert.deepEqual(facets.json().tags, ["planning", "work"]);

  await app.close();
});

test("app startup refreshes the SQLite index from vlog", async () => {
  const { config, db, vlogDir } = createTestContext();
  writeJson(path.join(vlogDir, "2026-06-29-0930.json"), baseMetadata());

  const app = buildApp({ config, db });
  const list = await app.inject({ method: "GET", url: "/api/recordings" });

  assert.equal(list.statusCode, 200);
  assert.equal(list.json().recordings.length, 1);
  await app.close();
});

test("recording guide API parses questions markdown into sections", async () => {
  const { config, db, repoRoot } = createTestContext();
  fs.mkdirSync(path.join(repoRoot, "docs"), { recursive: true });
  fs.writeFileSync(
    path.join(repoRoot, "docs", "questions.md"),
    [
      "# Recording Guide",
      "",
      "## Opening",
      "1. Why this recording?",
      "2. What happened recently?",
      "",
      "## Reflection",
      "- What felt useful?",
      "",
    ].join("\n"),
  );

  const app = buildApp({ config, db });
  const response = await app.inject({
    method: "GET",
    url: "/api/recording-guide",
  });

  assert.equal(response.statusCode, 200);
  assert.deepEqual(response.json().sections, [
    {
      title: "Opening",
      prompts: ["Why this recording?", "What happened recently?"],
    },
    {
      title: "Reflection",
      prompts: ["What felt useful?"],
    },
  ]);
  await app.close();
});

test("media thumbnail and duration are derived into app cache", async () => {
  const { config, db, repoRoot, vlogDir } = createTestContext();
  const ts = "2026-06-29-0930";
  fs.writeFileSync(path.join(vlogDir, `${ts}.mov`), "media");
  writeJson(path.join(vlogDir, `${ts}.json`), baseMetadata({ id: ts }));
  const fakeThumbnail = path.join(repoRoot, "scripts", "fake-thumbnail.py");
  fs.writeFileSync(
    fakeThumbnail,
    [
      "import pathlib",
      "import sys",
      "pathlib.Path(sys.argv[-1]).write_bytes(b'jpg')",
      "",
    ].join("\n"),
  );
  const fakeProbe = path.join(repoRoot, "scripts", "fake-ffprobe.py");
  fs.writeFileSync(
    fakeProbe,
    [
      "import json",
      "print(json.dumps({'format': {'duration': '12.5'}}))",
      "",
    ].join("\n"),
  );
  config.thumbnailCommand = ["python3", fakeThumbnail];
  config.ffprobeCommand = ["python3", fakeProbe];

  const app = buildApp({ config, db });
  const mediaInfo = await app.inject({
    method: "GET",
    url: `/api/recordings/${ts}/media-info`,
  });
  assert.equal(mediaInfo.statusCode, 200);
  assert.equal(mediaInfo.json().durationSeconds, 12.5);
  assert.equal(mediaInfo.json().thumbnailUrl, `/api/recordings/${ts}/thumbnail`);

  const thumbnail = await app.inject({
    method: "GET",
    url: `/api/recordings/${ts}/thumbnail`,
  });
  assert.equal(thumbnail.statusCode, 200);
  assert.equal(thumbnail.headers["content-type"], "image/jpeg");
  assert.equal(
    fs.existsSync(path.join(config.thumbnailDir, `${ts}.json`)),
    true,
  );
  assert.equal(
    fs.existsSync(path.join(config.thumbnailDir, `${ts}.jpg`)),
    true,
  );
  await app.close();
});

test("facets return real tags sorted by occurrence", async () => {
  const { config, db, vlogDir } = createTestContext();
  writeJson(path.join(vlogDir, "2026-06-29-0930.json"), baseMetadata());
  writeJson(
    path.join(vlogDir, "2026-06-29-0940.json"),
    baseMetadata({
      id: "2026-06-29-0940",
      timestamp_utc: "2026-06-29T04:10:00Z",
      timestamp_local: "2026-06-29T09:40:00+05:30",
      media_file: "2026-06-29-0940.mov",
      tags: ["work"],
    }),
  );

  const app = buildApp({ config, db });
  const facets = await app.inject({ method: "GET", url: "/api/facets" });

  assert.equal(facets.statusCode, 200);
  assert.deepEqual(facets.json().tags, ["work", "planning"]);
  assert.deepEqual(facets.json().tagCounts, { work: 2, planning: 1 });
  await app.close();
});

test("recordings API validates filters and paginates", async () => {
  const { config, db, vlogDir } = createTestContext();
  writeJson(path.join(vlogDir, "2026-06-29-0930.json"), baseMetadata());
  writeJson(
    path.join(vlogDir, "2026-06-29-0940.json"),
    baseMetadata({
      id: "2026-06-29-0940",
      timestamp_utc: "2026-06-29T04:10:00Z",
      timestamp_local: "2026-06-29T09:40:00+05:30",
      media_file: "2026-06-29-0940.mov",
    }),
  );
  refreshIndex(db, config);

  const app = buildApp({ config, db });
  const page = await app.inject({
    method: "GET",
    url: "/api/recordings?limit=1&offset=1",
  });
  assert.equal(page.statusCode, 200);
  assert.equal(page.json().pagination.count, 1);

  const badDate = await app.inject({
    method: "GET",
    url: "/api/recordings?date=2026-06",
  });
  assert.equal(badDate.statusCode, 400);

  const badQuality = await app.inject({
    method: "GET",
    url: "/api/recordings?metadata_quality=great",
  });
  assert.equal(badQuality.statusCode, 400);
  await app.close();
});

test("stop handles no active recording cleanly", async () => {
  const { config, db } = createTestContext();
  const app = buildApp({ config, db });

  const response = await app.inject({
    method: "POST",
    url: "/api/recordings/stop",
  });

  assert.equal(response.statusCode, 200);
  assert.equal(response.json().state, "idle");
  await app.close();
});

test("start returns conflict when a recording is already active", async () => {
  const { config, db, repoRoot } = createTestContext();
  fs.writeFileSync(
    path.join(repoRoot, "scripts", "privledger.py"),
    [
      "import signal",
      "import sys",
      "import time",
      "signal.signal(signal.SIGINT, lambda *_args: sys.exit(0))",
      "print('fake recorder started', flush=True)",
      "while True:",
      "    time.sleep(1)",
      "",
    ].join("\n"),
  );

  const app = buildApp({ config, db });
  const started = await app.inject({
    method: "POST",
    url: "/api/recordings/start",
  });
  assert.equal(started.statusCode, 200);
  assert.equal(started.json().state, "recording");

  const conflict = await app.inject({
    method: "POST",
    url: "/api/recordings/start",
  });
  assert.equal(conflict.statusCode, 409);

  const stopped = await app.inject({
    method: "POST",
    url: "/api/recordings/stop",
  });
  assert.equal(stopped.statusCode, 200);
  assert.equal(stopped.json().state, "idle");
  await app.close();
});

test("record command override drives start endpoint", async () => {
  const { config, db, repoRoot } = createTestContext();
  const fakeRecorder = path.join(repoRoot, "scripts", "fake-recorder.py");
  fs.writeFileSync(
    fakeRecorder,
    [
      "import signal",
      "import sys",
      "import time",
      "signal.signal(signal.SIGINT, lambda *_args: sys.exit(0))",
      "while True:",
      "    time.sleep(1)",
      "",
    ].join("\n"),
  );
  config.recordCommand = ["python3", fakeRecorder];

  const app = buildApp({ config, db });
  const started = await app.inject({
    method: "POST",
    url: "/api/recordings/start",
  });
  assert.equal(started.statusCode, 200);
  assert.equal(started.json().state, "recording");

  const stopped = await app.inject({
    method: "POST",
    url: "/api/recordings/stop",
  });
  assert.equal(stopped.statusCode, 200);
  assert.equal(stopped.json().state, "idle");
  await app.close();
});

test("record command strips interactive enrichment flag", () => {
  const config = createConfig({
    repoRoot: "/tmp/privledger-test-root",
    recordCommand: ["python3", "scripts/privledger.py", "--enrich"],
  });

  assert.deepEqual(config.recordCommand, ["python3", "scripts/privledger.py"]);
});

test("stop returns latest recording created by recorder process", async () => {
  const { config, db, repoRoot, vlogDir } = createTestContext();
  writeJson(
    path.join(vlogDir, "2026-06-29-1020.json"),
    baseMetadata({
      id: "2026-06-29-1020",
      timestamp_utc: "2026-06-29T04:50:00Z",
      timestamp_local: "2026-06-29T10:20:00+05:30",
      media_file: "2026-06-29-1020.mov",
      tags: [],
    }),
  );
  const fakeRecorder = path.join(repoRoot, "scripts", "fake-recorder.py");
  fs.writeFileSync(
    fakeRecorder,
    [
      "import json",
      "import pathlib",
      "import signal",
      "import sys",
      "import time",
      `vlog = pathlib.Path(${JSON.stringify(vlogDir)})`,
      "def stop(*_args):",
      "    ts = '2026-06-29-1010'",
      "    (vlog / f'{ts}.mov').write_text('media')",
      "    (vlog / f'{ts}.json').write_text(json.dumps({",
      "        'id': ts,",
      "        'timestamp_utc': '2026-06-29T04:40:00Z',",
      "        'timestamp_local': '2026-06-29T10:10:00+05:30',",
      "        'schema_version': 1,",
      "        'pipeline_version': '0.1.0',",
      "        'metadata_quality': 'basic',",
      "        'media_file': f'{ts}.mov',",
      "        'video_device': 'fake',",
      "        'transcript_file': None,",
      "        'tags': []",
      "    }))",
      "    print(f'Metadata written -> {ts}.json', flush=True)",
      "    sys.exit(0)",
      "signal.signal(signal.SIGINT, stop)",
      "while True:",
      "    time.sleep(1)",
      "",
    ].join("\n"),
  );
  config.recordCommand = ["python3", fakeRecorder];

  const app = buildApp({ config, db });
  await app.inject({ method: "POST", url: "/api/recordings/start" });
  await new Promise((resolve) => setTimeout(resolve, 100));
  const stopped = await app.inject({ method: "POST", url: "/api/recordings/stop" });

  assert.equal(stopped.statusCode, 200);
  assert.equal(stopped.json().recordingId, "2026-06-29-1010");
  assert.equal(stopped.json().latestRecording.id, "2026-06-29-1010");
  assert.equal(stopped.json().latestRecording.quality, "basic");
  await app.close();
});

test("enrichment API delegates describe and submit to enrich script", async () => {
  const { config, db, repoRoot, vlogDir } = createTestContext();
  const ts = "2026-06-29-0930";
  writeJson(path.join(vlogDir, `${ts}.json`), baseMetadata({ id: ts }));
  refreshIndex(db, config);

  const fakeEnrich = path.join(repoRoot, "scripts", "fake-enrich.py");
  fs.writeFileSync(
    fakeEnrich,
    [
      "import json",
      "import pathlib",
      "import sys",
      `vlog = pathlib.Path(${JSON.stringify(vlogDir)})`,
      "mode, ts = sys.argv[1], sys.argv[2]",
      "if mode == '--describe':",
      "    print(json.dumps({'id': ts, 'tag_vocabulary': ['planning', 'sleep'], 'custom': {'enabled': False, 'schema_hash': None, 'fields': []}}))",
      "elif mode == '--json':",
      "    payload = json.load(sys.stdin)",
      "    path = vlog / f'{ts}.json'",
      "    data = json.loads(path.read_text())",
      "    data.update(payload)",
      "    path.write_text(json.dumps(data))",
      "    print(json.dumps({'ok': True, 'id': ts, 'metadata': data, 'changed': sorted(payload), 'field_errors': {}, 'message': None}))",
      "else:",
      "    sys.exit(2)",
      "",
    ].join("\n"),
  );
  config.enrichCommand = ["python3", fakeEnrich];

  const app = buildApp({ config, db });
  const described = await app.inject({
    method: "GET",
    url: `/api/recordings/${ts}/enrichment`,
  });
  assert.equal(described.statusCode, 200);
  assert.deepEqual(described.json().tag_vocabulary, ["planning", "sleep"]);

  const submitted = await app.inject({
    method: "POST",
    url: `/api/recordings/${ts}/enrichment`,
    payload: { mood: 5, tags: ["sleep"] },
  });
  assert.equal(submitted.statusCode, 200);

  const full = await app.inject({ method: "GET", url: `/api/recordings/${ts}/full` });
  assert.equal(full.json().life.mood, 5);
  assert.deepEqual(full.json().life.tags, ["sleep"]);
  await app.close();
});

test("enrichment describe does not require a preexisting SQLite row", async () => {
  const { config, db, repoRoot, vlogDir } = createTestContext();
  const ts = "2026-06-29-0930";
  const fakeEnrich = path.join(repoRoot, "scripts", "fake-enrich.py");
  fs.writeFileSync(
    fakeEnrich,
    [
      "import json",
      "import pathlib",
      "import sys",
      `vlog = pathlib.Path(${JSON.stringify(vlogDir)})`,
      "mode, ts = sys.argv[1], sys.argv[2]",
      "if mode == '--describe':",
      "    json.loads((vlog / f'{ts}.json').read_text())",
      "    print(json.dumps({'id': ts, 'tag_vocabulary': ['work'], 'custom': {'enabled': False, 'schema_hash': None, 'fields': []}}))",
      "else:",
      "    sys.exit(2)",
      "",
    ].join("\n"),
  );
  config.enrichCommand = ["python3", fakeEnrich];

  const app = buildApp({ config, db });
  writeJson(path.join(vlogDir, `${ts}.json`), baseMetadata({ id: ts }));

  const described = await app.inject({
    method: "GET",
    url: `/api/recordings/${ts}/enrichment`,
  });

  assert.equal(described.statusCode, 200);
  assert.deepEqual(described.json().tag_vocabulary, ["work"]);
  await app.close();
});

test("enrichment API preserves structured validation errors", async () => {
  const { config, db, repoRoot, vlogDir } = createTestContext();
  const ts = "2026-06-29-0930";
  writeJson(path.join(vlogDir, `${ts}.json`), baseMetadata({ id: ts }));
  refreshIndex(db, config);

  const fakeEnrich = path.join(repoRoot, "scripts", "fake-enrich-error.py");
  fs.writeFileSync(
    fakeEnrich,
    [
      "import json",
      "import sys",
      "mode, ts = sys.argv[1], sys.argv[2]",
      "if mode == '--json':",
      "    print(json.dumps({'ok': False, 'id': ts, 'metadata': {'id': ts}, 'changed': [], 'field_errors': {'tags': 'tags must exist in configured tag vocabulary'}, 'message': 'Validation failed'}))",
      "    sys.exit(1)",
      "print(json.dumps({'id': ts, 'tag_vocabulary': [], 'custom': {'enabled': False, 'schema_hash': None, 'fields': []}}))",
      "",
    ].join("\n"),
  );
  config.enrichCommand = ["python3", fakeEnrich];

  const app = buildApp({ config, db });
  const response = await app.inject({
    method: "POST",
    url: `/api/recordings/${ts}/enrichment`,
    payload: { tags: ["bad"] },
  });

  assert.equal(response.statusCode, 400);
  assert.equal(response.json().field, "tags");
  assert.equal(response.json().field_errors.tags, "tags must exist in configured tag vocabulary");
  assert.match(response.json().error, /Validation failed/);
  await app.close();
});
