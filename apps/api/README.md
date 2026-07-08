# Privledger API

Local Fastify API for indexing and controlling the Privledger recording pipeline.

`vlog/` is the source of truth. SQLite is a disposable cache at
`.privledger/privledger-index.sqlite`.

## Commands

```bash
cd apps/api
npm install
npm run dev
npm test
npm run build
```

The dev server listens on `127.0.0.1:4577` by default.

## Environment

- `PRIVLEDGER_ROOT`: repo root override.
- `PRIVLEDGER_INDEX_DB`: SQLite cache path override.
- `PRIVLEDGER_API_HOST`: host override.
- `PRIVLEDGER_API_PORT`: port override.
- `PRIVLEDGER_RECORD_COMMAND`: command used by `POST /api/recordings/start`.
- `PRIVLEDGER_TRANSCRIBE_COMMAND`: command used by `POST /api/transcripts/transcribe-missing`.

Command overrides are whitespace-split and executed directly, not through a shell.

## Main Endpoints

```text
GET  /api/health
GET  /api/status
POST /api/index/refresh

GET  /api/recordings
GET  /api/recordings/:id
GET  /api/recordings/:id/full
GET  /api/recordings/:id/metadata
GET  /api/recordings/:id/transcript
GET  /api/recordings/:id/media

GET  /api/calendar?month=YYYY-MM
GET  /api/facets

POST /api/recordings/start
POST /api/recordings/stop
POST /api/transcripts/transcribe-missing
```

`GET /api/recordings` supports:

```text
date=YYYY-MM-DD
from=YYYY-MM-DD
to=YYYY-MM-DD
metadata_quality=basic|full|corrected|bad
has_transcript=true|false
tag=TAG
q=FTS_QUERY
limit=1..200
offset=0+
```

## Response Shape

List/detail responses use UI-facing DTOs instead of raw SQLite rows:

```json
{
  "id": "2026-06-28-2250",
  "startedAt": {
    "utc": "2026-06-28T22:50:30Z",
    "local": "2026-06-29T04:20:30+05:30",
    "dateLocal": "2026-06-29"
  },
  "quality": "basic",
  "media": {
    "file": "2026-06-28-2250.mov",
    "exists": true,
    "url": "/api/recordings/2026-06-28-2250/media",
    "device": "brio"
  },
  "transcript": {
    "file": null,
    "exists": false,
    "language": null,
    "segmentCount": null,
    "preview": null,
    "url": null
  },
  "life": {
    "mood": 3,
    "energy": 4,
    "stress": 2,
    "sleepiness": 1,
    "sleepHours": 7.5,
    "caffeineMg": 120,
    "bodyWeight": 70,
    "focusDomain": "programming",
    "tags": ["job", "planning"],
    "location": "desk"
  },
  "index": {
    "status": "ok",
    "error": null
  }
}
```

Raw source files remain available through `/metadata` and `/transcript`.
