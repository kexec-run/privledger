# Privledger Architecture

Pipeline: capture → classify → commit

Single session = one timestamp = one classification = one metadata record

## Data Flow

```
user
↓
scripts/privledger.py        # load env + schema, generate timestamp, supervise process
↓
scripts/record.sh            # device checks, run ffmpeg, manage lifecycle
↓
ffmpeg                       # capture → temp file (TS.mkv.tmp.<pid>)
↓
record.sh                    # validate (duration advisory, exit non-authoritative)
↓
filesystem
├── TS.mkv                   # success
├── TS.mkv.bad.mkv           # degraded
└── (no file)                # preflight failure
↓
scripts/privledger.py        # classify state (filesystem is authoritative, exit code advisory)
↓
metadata/writer.py           # build + validate + atomic write
↓
vlog/TS.json                 # final metadata
```

### Optional (User Mutation)

```
scripts/enrich.py            # load TS.json → prompt user → update fields
↓
metadata/writer.py           # validate + atomic overwrite
↓
vlog/TS.json
```

---

## Stage Contracts

| Stage | Input | Output | Purpose |
|---|---|---|---|
| privledger.py | env + schema | TIMESTAMP + process | orchestrate capture |
| record.sh | TIMESTAMP + env | `.mkv` / `.bad.mkv` / none | produce media artifact |
| ffmpeg | devices | temp file | encode audio/video |
| record.sh (post) | temp file | final file | validate + finalize |
| privledger.py (post) | filesystem | classification | determine outcome |
| writer.py | metadata fields | `.json` | validate + persist |
| enrich.py | `.json` | updated `.json` | user-driven enrichment |

---

## Execution Model

- single-run process
- one timestamp per session
- no parallel pipeline
- blocking execution (waits for capture completion)

---

## Artifact Model

Exactly one of:
- `TS.mkv`
- `TS.mkv.bad.mkv`
- (no file)

must exist per session.

Metadata exists only if a media artifact exists and validation succeeds.

---

## Metadata Fields

Required (schema-enforced):
`id`, `timestamp_utc`, `schema_version`, `pipeline_version`, `metadata_quality`, `media_file`

Auto-populated by capture: `timestamp_local`, `video_device`

Nullable, user-populated via enrich: `mood`, `energy`, `stress`, `sleepiness`, `sleep_hours`, `caffeine_mg`, `body_weight`, `focus_domain`, `tags`, `location`

Deferred population: `transcript_file`

Constraints:
- `tags`: max 5, unique
- numeric fields bounded (1–5 or ≥ 0)
- no unknown fields (schema rejects additionalProperties)

Schema contract: `tests/schema/metadata.v1.schema.json`

---

## Directory Structure

```
.
├── config/
│   ├── env                          # runtime configuration (devices, versions)
│   └── tags.txt                     # controlled vocabulary for tagging
│
├── docs/
│   ├── arch.md                      # system architecture (this file)
│   └── tags.md                      # tag semantics and usage rules
│
├── logs/                            # capture logs (per session, ffmpeg output)
│
├── metadata/
│   ├── __init__.py
│   ├── validator.py                 # schema validation wrapper
│   └── writer.py                    # metadata construction + atomic write
│
├── scripts/
│   ├── privledger.py                # supervisor / entrypoint
│   ├── record.sh                    # capture pipeline (ffmpeg wrapper)
│   ├── enrich.py                    # metadata enrichment CLI
│   └── test_writer.py               # manual smoke test (not part of pipeline)
│
├── tests/
│   └── schema/
│       └── metadata.v1.schema.json  # metadata contract
│
├── vlog/                            # primary data store (media + metadata)
│   ├── TS.mkv
│   ├── TS.mkv.bad.mkv
│   └── TS.json
│
├── README.md
├── requirements.txt
└── TODO.md
```

### Structure Principles

| Directory | Role |
|---|---|
| `vlog/` | durable data store — source of truth |
| `logs/` | disposable execution traces — debug / audit |
| `metadata/` | data layer (validation + persistence) |
| `scripts/` | entrypoints and orchestration |
| `config/` | runtime inputs |
| `docs/` | contracts and semantics |
| `tests/` | verification |

`vlog/` and `logs/` are distinct by durability:
you can delete `logs/` and lose nothing meaningful.
You should never delete `vlog/`.

---

## Failure Matrix

| Condition | Artifact | Metadata | Exit Code |
|---|---|---|---|
| Successful capture | `TS.mkv` | written (`basic`) | 0 |
| Degraded capture (any failure after start) | `TS.mkv.bad.mkv` | written (`bad`) | non-zero |
| Preflight failure (no capture started) | none | none | non-zero |
| Invariant violation (both files exist) | both | none | 2 |
| Metadata validation/write failure | `TS.mkv` or `.bad.mkv` | none | 1 |

- Filesystem determines classification, not exit code.
- Metadata is written only after artifact classification succeeds.
- Media artifacts are never deleted on failure.
