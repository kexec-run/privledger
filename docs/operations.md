# Operations

This doc covers local setup, commands, recording, enrichment, and verification.

## Requirements

The repository has two capture backends:

- **Linux:** Python dependencies from `requirements.txt`, ffmpeg built with VAAPI, `pactl` from PulseAudio or PipeWire, and a v4l2 camera under `/dev/video*`. Set `VIDEO_DEV`, `AUDIO_SRC`, and `VAAPI_DEV` in `config/env`.
- **macOS:** Python dependencies, ffmpeg/ffprobe, the `tools/avcam-cli` submodule, and Camera and Microphone permissions for the process launching the API or CLI. Set the camera device in `config/env` as needed by the helper.

Use a Python virtual environment before installing `requirements.txt`. Keep runtime configuration in the ignored `config/env`; `config/env.sample` contains the public template. For browser-based capture, grant permissions to the terminal or app that launched `scripts/dev.sh`.

## Device Discovery

On Linux, inspect available devices with:

```bash
ls /dev/video*
ls /dev/dri/render*
pactl list short sources
ffmpeg -hwaccels | grep vaapi
```

Set the selected camera, audio source, and render device in `config/env`. If VAAPI is not listed by ffmpeg, hardware encoding will not work.

On macOS, initialize the camera helper with `git submodule update --init --recursive`. Build it from `tools/avcam-cli` if the checked-out helper does not include a usable binary. Confirm Camera and Microphone permissions for the process context running the recorder. Sandboxed automation can report `Camera access is denied` even when the command works from a permitted terminal.

## Commands

Start the API and web app:

```bash
./scripts/dev.sh start
./scripts/dev.sh status
./scripts/dev.sh restart
./scripts/dev.sh stop
```

The dashboard is served at `http://127.0.0.1:5173`; the API is at `http://127.0.0.1:4577`. Install Node dependencies in both `apps/api` and `apps/web` before starting.

Run the Python recorder directly:

```bash
python3 scripts/privledger.py
```

The script selects `scripts/record-mac.sh` on macOS and `scripts/record-linux.sh` on Linux. Stop it with Ctrl+C.

Run capture and open the CLI enrichment after a clean non-bad artifact:

```bash
python3 scripts/privledger.py --enrich
```

Enrich an existing session:

```bash
python3 scripts/enrich.py 2026-02-27-0727.json
```

The argument may be a timestamp, JSON filename, media filename, or path that resolves to a timestamp.

Run focused behavior tests and lint:

```bash
PYTHONPATH=. python3 -m pytest tests/test_writer_invariants.py tests/test_enrich_behavior.py -q
uv run ruff check .
```

## Recording Output

Recording writes to `vlog/`. Possible media outcomes include `TS.mkv`, `TS.mov`, their `.bad` variants, or no media artifact. Metadata is written as `vlog/TS.json`; transcripts are stored under `vlog/transcripts/`. These files are durable source data. Logs under `logs/` and the SQLite database/thumbnails under `.privledger/` are derived or disposable.

## Camera Test Constraint

Real camera tests require a macOS process with Camera and Microphone permission. In environments without those permissions, use the isolated fake-recorder browser suite. The opt-in real-recorder browser test uses the local configuration and camera helper, but puts generated media and metadata in a temporary test workspace.

## Verification

For Python changes, run the narrow relevant tests and `uv run ruff check .`. For API/web changes, use the package scripts and the isolated UI suite documented in [ui-test.md](ui-test.md). `basedpyright` is optional and is not part of the required verification gate.
