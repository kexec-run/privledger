# Privledger Architecture

Privledger is a filesystem-authoritative recording and metadata pipeline.

For operational docs, see:

- [operations.md](./operations.md) - setup, commands, recording, and verification
- [metadata.md](./metadata.md) - schema fields, writers, validation, and tag/focus invariants
- [enrichment.md](./enrichment.md) - user-editable metadata, prompts, typo resolution, and re-prompt behavior
- [tags.md](./tags.md) - tag semantics and vocabulary rules
- [test.md](./test.md) - behavior matrix and failure cases

## Core Principle

The filesystem determines capture outcome. Process exit codes are advisory.

Single session = one timestamp = one media classification = one metadata record.

## Layer Boundaries

Each layer owns one class of responsibility. Cross-layer leakage should be treated as an architectural problem.

| Layer | Owns | Must Not Own |
|---|---|---|
| `scripts/record.sh` | media capture, temporary file lifecycle, final media artifact | metadata classification |
| `scripts/privledger.py` | orchestration, timestamp generation, artifact classification | user enrichment prompts |
| filesystem | capture outcome evidence | schema interpretation |
| `metadata/writer.py` | metadata construction, invariant check, schema validation, atomic write | user interaction |
| `metadata/check.py` | strict stored-data invariants | fuzzy typo correction |
| `metadata/tags.py` | exact tag vocabulary loading and tag/focus predicates | prompt UI |
| `scripts/enrich.py` | user input, typo resolution, re-prompt behavior | durable invariant definitions |
| `tests/` | behavior verification | changing production behavior |

## Data Flow

```text
user
↓
scripts/privledger.py        # load env + schema, generate timestamp, supervise process
↓
scripts/record.sh            # device checks, run ffmpeg, manage lifecycle
↓
ffmpeg                       # capture → temp file (TS.mkv.tmp.<pid>)
↓
record.sh                    # validate duration advisory, finalize media artifact
↓
filesystem
├── TS.mkv                   # successful artifact
├── TS.mkv.bad.mkv           # degraded artifact
└── no file                  # preflight failure
↓
scripts/privledger.py        # classify state from filesystem
↓
metadata/writer.py           # build + validate + atomic write
↓
vlog/TS.json                 # final metadata
```

Optional enrichment:

```text
scripts/enrich.py            # load TS.json → prompt user → update mutable fields
↓
metadata/writer.py           # validate + atomic overwrite
↓
vlog/TS.json
```

## Stage Contracts

| Stage | Input | Output | Purpose |
|---|---|---|---|
| `privledger.py` | env + schema | timestamp + recorder process | orchestrate capture |
| `record.sh` | timestamp + env | `.mkv`, `.bad.mkv`, or no artifact | produce media artifact |
| `ffmpeg` | devices | temp media file | encode audio/video |
| `record.sh` post | temp file | final media artifact | validate + finalize |
| `privledger.py` post | filesystem | classification | determine outcome |
| `writer.py` | metadata fields | `.json` | validate + persist |
| `enrich.py` | existing `.json` | updated `.json` | user-driven enrichment |

## Artifact Model

Exactly one of these should exist per session:

- `TS.mkv`
- `TS.mkv.bad.mkv`
- no media artifact

Both `TS.mkv` and `TS.mkv.bad.mkv` for the same timestamp is an invariant violation.

Metadata exists only if a media artifact exists and metadata validation succeeds.

## Invariants

These invariants describe boundaries that should remain true as the project evolves.

- A1: The filesystem is authoritative for capture classification; recorder exit status is advisory.
- A2: A session has one timestamp and at most one final media artifact.
- A3: Metadata is written only after media artifact classification succeeds.
- A4: Media artifacts are not deleted when metadata validation or writing fails.
- A5: `metadata/writer.py` is the only production path that constructs and atomically writes metadata.
- A6: `metadata/check.py` validates stored-data invariants strictly; it does not interpret typos.
- A7: `metadata/tags.py` owns exact tag vocabulary loading and reusable tag/focus predicates.
- A8: `scripts/enrich.py` resolves human input before validation; it must not redefine durable tag/focus rules.
- A9: Schema validation rejects unknown fields and shape-level metadata violations.
- A10: Tests should encode documented behavior before behavior is changed.

## Failure Matrix

| Condition | Artifact | Metadata | Exit Code |
|---|---|---|---|
| Successful capture | `TS.mkv` | written as `basic` | `0` |
| Degraded capture after start | `TS.mkv.bad.mkv` | written as `bad` | non-zero |
| Preflight failure | none | none | non-zero |
| Both good and bad artifacts exist | both | none | `2` |
| Metadata validation/write failure | media artifact remains | none | `1` |

## Project Tree

Generated artifacts and local data volume details are omitted.

```text
.
├── config/ - runtime configuration and controlled vocabularies
│   ├── env
│   └── tags.txt
├── docs/ - contracts and operating notes
│   ├── arch.md
│   ├── enrichment.md
│   ├── metadata.md
│   ├── operations.md
│   ├── questions.md
│   ├── tags.md
│   └── test.md
├── logs/ - disposable capture logs
├── metadata/ - validation and persistence layer
├── scripts/ - command entrypoints and orchestration
├── tests/ - behavior and schema verification
└── vlog/ - durable media and metadata store
```

## Known Tradeoffs

- The current CLI prompt is linear. It rejects invalid focus/tag states and re-prompts, but it does not yet offer a full tag-removal UI.
- The test matrix currently records a supervisor deviation: a `.bad.mkv` artifact with recorder exit `0` should be treated as failure, but the current behavior still returns success.
- Webcam-dependent recording behavior is tested through mocks because local macOS camera capture is not available in this environment.
