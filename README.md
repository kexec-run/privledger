# privledger

Video ledger that captures daily entries to reveal patterns and personal growth over time.

README is the entrypoint. Detailed contracts live under `docs/`.

## Principles

- Append-only history
- Atomic capture first
- Structured metadata
- Human-first, analysis-ready
- Local durability

## Status

Capture pipeline exists. Metadata writes are schema-validated and atomic. Enrichment CLI is functional. Tag/focus invariants are encoded in tests. Active development is focused on hardening capture classification and enrichment workflow.

Known current deviation: the supervisor behavior matrix has one failing case where a `.bad.mkv` artifact with recorder exit `0` still returns success.

## Quick Start

Install Python dependencies:

```bash
pip install --user -r requirements.txt
```

Copy runtime config:

```bash
cp config/env.sample config/env
```

Edit `config/env` with device and version values.

Run capture:

```bash
python3 scripts/privledger.py
```

Run capture and open enrichment after a clean recording:

```bash
python3 scripts/privledger.py --enrich
```

Enrich metadata:

```bash
python3 scripts/enrich.py vlog/TS.json
```

Run focused behavior tests:

```bash
PYTHONPATH=. pytest tests/test_writer_invariants.py tests/test_enrich_behavior.py -q
```

## Docs

- [Architecture](docs/arch.md) - data flow, layer boundaries, invariants, failure matrix
- [Operations](docs/operations.md) - setup, commands, recording, enrichment, verification
- [Metadata](docs/metadata.md) - schema fields, writers, validation, stored-data invariants
- [Enrichment](docs/enrichment.md) - prompt flow, typo resolution, focus-domain behavior
- [Tags](docs/tags.md) - tag semantics, definitions, and usage rules
- [Test Matrix](docs/test.md) - behavior matrix and failure cases
- [Recording Guide](docs/questions.md) - what to say when you don't know what to say while recording

## Tasks

See [TODO.md](TODO.md) for current status and planned work.

## Requirements

### Core

- Python 3.10+
- ffmpeg with VAAPI support
- PulseAudio / PipeWire (with `pactl` available)
- v4l2 (video devices exposed under `/dev/video*`)

Verify VAAPI support:

```bash
ffmpeg -hwaccels | grep vaapi
```

If `vaapi` is not listed, hardware encoding will not work.

### Python packages

Install locally (user scope recommended):

```bash
pip install --user -r requirements.txt
```

If your system restricts user installs, add `--break-system-packages`.

Ensure user-level binaries are in PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add to your shell config (`.bashrc`, `.zshrc`) for persistence.

### Optional

- `mpv` - video playback verification
- `jq` - JSON inspection
- `v4l-utils` - device inspection via `v4l2-ctl`

These are not required for pipeline execution.

## Configuration

All runtime configuration is defined in `config/env`.

```bash
cp config/env.sample config/env
```

Then edit `config/env` with your device values.

Required variables:

- `VIDEO_DEV` - video device path
- `AUDIO_SRC` - PulseAudio source name
- `VAAPI_DEV` - VAAPI device, for example `/dev/dri/renderD128`
- `SCHEMA_VERSION`
- `PIPELINE_VERSION`

Device discovery and troubleshooting details live in [docs/operations.md](docs/operations.md).

## Usage

Use `python3` explicitly to avoid system differences.

### Capture

Run from repository root:

```bash
python3 scripts/privledger.py
```

Press `Ctrl+C` to stop recording with graceful shutdown.

To open enrichment automatically after a clean non-bad recording:

```bash
python3 scripts/privledger.py --enrich
```

Output is written to `vlog/`:

```text
vlog/
  TS.mkv           Linux successful capture
  TS.mkv.bad.mkv   Linux degraded capture
  TS.mov           macOS successful capture
  TS.mov.bad.mov   macOS degraded capture
  TS.json          metadata
```

### Enrich metadata

```bash
python3 scripts/enrich.py vlog/TS.json
```

The argument may also be a timestamp, media filename, or path that resolves to a timestamp.

### Inspect metadata

```bash
cat vlog/TS.json | jq .
```

### Playback

```bash
mpv vlog/TS.mkv
```

## Verification

Run focused invariant and enrichment tests:

```bash
PYTHONPATH=. pytest tests/test_writer_invariants.py tests/test_enrich_behavior.py -q
```

Run supervisor and custom-check behavior tests:

```bash
PYTHONPATH=. pytest tests/test_supervisor_behavior.py tests/test_check.py -q
```

Run lint:

```bash
uv run ruff check .
```

`basedpyright` is currently noisy and not a useful required gate for this phase.

## Invariant Summary

- Filesystem state determines capture classification.
- A session has one timestamp and at most one final media artifact.
- Metadata writes are validated and atomic.
- `focus_domain` is a primary tag stored separately from regular `tags`.
- Tag typo input resolves to canonical values before stored-data validation.
- Prompt validation re-prompts when the user can correct input.

## Troubleshooting

- No output file: check `logs/` for the session log.
- Capture fails immediately: verify `VIDEO_DEV` and `AUDIO_SRC` in `config/env`.
- Metadata validation fails: check [docs/metadata.md](docs/metadata.md) and [docs/test.md](docs/test.md).
- Enrichment rejects a tag or focus domain: check [docs/enrichment.md](docs/enrichment.md) and [docs/tags.md](docs/tags.md).
