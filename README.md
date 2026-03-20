# privledger

Video ledger that captures daily entries to reveal patterns and personal growth over time.

## Principles

- Append-only history
- Atomic capture first
- Structured metadata
- Human-first, analysis-ready
- Local durability

## Status

Capture pipeline stable. Metadata layer wired and schema-validated. Enrich CLI functional. Active development on hardening and enrichment workflow.

## Docs

- [Architecture](docs/arch.md) — data flow, stage contracts, directory structure
- [Tags](docs/tags.md) — tag semantics, definitions, and usage rules

## Tasks

See [TODO.md](TODO.md) for current status and planned work.

---

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
# or manually
pip install --user python-dotenv jsonschema
```

If your system restricts user installs, add `--break-system-packages`.

Ensure user-level binaries are in PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add to your shell config (`.bashrc`, `.zshrc`) for persistence.

Verify:

```bash
which python3
python3 -c "import dotenv, jsonschema"
```

### Optional

- `mpv` — video playback verification
- `jq` — JSON inspection
- `v4l-utils` — device inspection via `v4l2-ctl`

These are not required for pipeline execution.

---

## Configuration

All runtime configuration is defined in `config/env`.

### Setup

Copy the sample config:

```bash
cp config/env.sample config/env
```

Then edit `config/env` with your device values.

### Required variables

- `VIDEO_DEV` — video device path
- `AUDIO_SRC` — PulseAudio source name
- `VAAPI_DEV` — VAAPI device (e.g. `/dev/dri/renderD128`)
- `SCHEMA_VERSION`
- `PIPELINE_VERSION`

### Video device discovery

Prefer `/dev/videoX` for initial setup.
Use `/dev/v4l/by-id/` only if you need stable device mapping.

**Step 1: find available devices**

```bash
ls /dev/video*
```

**Step 2: test the device**

```bash
ffmpeg -f v4l2 -input_format mjpeg -i /dev/video0 -frames:v 1 test.jpg
```

If this fails, try a different `/dev/videoX`.

**Optional: get stable path**

```bash
ls /dev/v4l/by-id/
```

### Audio source discovery

```bash
pactl list short sources
```

Pick the correct input (mic or webcam).

### Example config/env

```
VIDEO_DEV=/dev/video0
AUDIO_SRC=alsa_input.usb-XXXX.mono-fallback
VAAPI_DEV=/dev/dri/renderD128
SCHEMA_VERSION=1
PIPELINE_VERSION=0.1.0
```

---

## Usage

Use `python3` explicitly to avoid system differences.

### Capture

Run from repository root:

```bash
python3 scripts/privledger.py
```

Press `Ctrl+C` to stop recording (graceful shutdown).

Output is written to `vlog/`:

```
vlog/
  TS.mkv
  TS.mkv.bad.mkv   (degraded capture)
  TS.json          (metadata)
```

### Enrich metadata

```bash
python3 scripts/enrich.py vlog/TS.mkv
```

or

```bash
python3 scripts/enrich.py vlog/TS.json
```

### Inspect metadata (optional)

```bash
cat vlog/TS.json | jq .
```

### Playback (optional)

```bash
mpv vlog/TS.mkv
```

---

## Troubleshooting

- No output file → check `logs/` for the session log
- Capture fails immediately → verify `VIDEO_DEV` and `AUDIO_SRC` in `config/env`
- Audio missing or wrong source → run `pactl list short sources` and update `AUDIO_SRC`
- VAAPI error → run `ffmpeg -hwaccels | grep vaapi` to confirm hardware support
- Python package not found → verify PATH includes `$HOME/.local/bin`
