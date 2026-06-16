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
| `config/` | local runtime inputs and controlled vocabulary files | capture classification or validation logic |
| `scripts/record-linux.sh` / `scripts/record-mac.sh` | media capture, temporary file lifecycle, final media artifact | metadata classification |
| `scripts/privledger.py` | platform detection, shared orchestration, timestamp generation, artifact classification, metadata write | user enrichment prompts |
| `scripts/privledger-linux.py` / `scripts/privledger-mac.py` | debug-only platform recorder configuration shims | duplicated metadata logic |
| filesystem | capture outcome evidence | schema interpretation |
| `metadata/writer.py` | metadata construction, invariant check, schema validation, atomic write | user interaction |
| `metadata/check.py` | strict stored-data invariants | fuzzy typo correction |
| `metadata/tags.py` | exact tag vocabulary loading and tag/focus predicates | prompt UI |
| `metadata/custom_schema.py` | custom metadata schema loading and type normalization | prompt rendering or persistence |
| `metadata/validator.py` | JSON schema validation wrapper | semantic invariant definitions |
| `scripts/enrich.py` | user input, typo resolution, re-prompt behavior | durable invariant definitions |
| `tests/schema/` | JSON schema contract fixtures | runtime schema mutation |
| `tests/` | behavior verification and mock capture cases | changing production behavior |

## Data Flow

```text
user
↓
scripts/privledger.py        # detect platform, load env/schema, timestamp, supervision, metadata write
↓
scripts/record-linux.sh      # Linux: device checks, run ffmpeg, manage lifecycle
or scripts/record-mac.sh     # macOS: run avcam-cli, manage lifecycle
↓
ffmpeg or avcam-cli          # capture → temp file
↓
record script                # validate duration advisory, finalize media artifact
↓
filesystem
├── TS.mkv / TS.mov          # successful artifact
├── TS.mkv.bad.mkv / TS.mov.bad.mov
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
| `privledger.py` | platform + env + schema | timestamp + recorder process + metadata | platform selection and shared supervision |
| `privledger-linux.py` / `privledger-mac.py` | debug flag | forced platform config | platform-specific debugging only |
| `record-linux.sh` / `record-mac.sh` | timestamp + env | media artifact, bad artifact, or no artifact | produce media artifact |
| `ffmpeg` | devices | temp media file | encode audio/video |
| recorder script post | temp file | final media artifact | validate + finalize |
| `privledger.py` post | filesystem | classification | determine outcome |
| `writer.py` | metadata fields | `.json` | validate + persist |
| `enrich.py` | existing `.json` | updated `.json` | user-driven enrichment |

## Artifact Model

Exactly one of these should exist per session:

- `TS.mkv`
- `TS.mkv.bad.mkv`
- `TS.mov`
- `TS.mov.bad.mov`
- no media artifact

Both good and bad artifacts for the same timestamp are an invariant violation. For example, `TS.mkv` plus `TS.mkv.bad.mkv`, or `TS.mov` plus `TS.mov.bad.mov`.

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
│   ├── custom_schema.yaml
│   ├── env
│   ├── env.sample
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
│   └── .gitkeep
├── metadata/ - validation and persistence layer
│   ├── __init__.py
│   ├── check.py
│   ├── custom_schema.py
│   ├── tags.py
│   ├── validator.py
│   └── writer.py
├── scripts/ - command entrypoints and orchestration
│   ├── enrich.py
│   ├── privledger.py
│   ├── privledger-linux.py
│   ├── privledger-mac.py
│   ├── record-linux.sh
│   ├── record-mac.sh
│   └── test_writer.py
├── tests/ - behavior and schema verification
│   ├── schema/
│   │   └── metadata.v1.schema.json
│   ├── test_check.py
│   ├── test_enrich_behavior.py
│   ├── test_supervisor_behavior.py
│   └── test_writer_invariants.py
├── vlog/ - durable media and metadata store
│   ├── .gitkeep
│   └── TS.json / TS.mkv / TS.mkv.bad.mkv / TS.mov / TS.mov.bad.mov
├── .pre-commit-config.yaml
├── AGENTS.md
├── README.md
├── requirements.txt
└── TODO.md
```

## Known Tradeoffs

- The current CLI prompt is linear. It rejects invalid focus/tag states and re-prompts, but it does not yet offer a full tag-removal UI.
- The test matrix currently records a supervisor deviation: a `.bad.mkv` artifact with recorder exit `0` should be treated as failure, but the current behavior still returns success.
- Webcam-dependent recording behavior is tested through mocks unless the process has macOS camera and microphone permission.
