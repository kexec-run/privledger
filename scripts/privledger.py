#!/usr/bin/env python3

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from metadata.writer import write_metadata_atomic

###############################################################################
# Paths and environment
###############################################################################

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_ENV = ROOT_DIR / "config" / "env"
RECORD_SCRIPT = ROOT_DIR / "scripts" / "record.sh"
SCHEMA_PATH = ROOT_DIR / "tests" / "schema" / "metadata.v1.schema.json"

# Load config/env
if not CONFIG_ENV.exists():
    print("[privledger] ERROR: config/env missing", file=sys.stderr)
    sys.exit(1)

load_dotenv(CONFIG_ENV)

SCHEMA_VERSION = os.getenv("SCHEMA_VERSION")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION")

if not SCHEMA_VERSION or not PIPELINE_VERSION:
    print("[privledger] ERROR: missing required env values", file=sys.stderr)
    sys.exit(1)

###############################################################################
# Environment validation (authoritative from config/env)
###############################################################################

ENV = os.environ.copy()

REQUIRED_ENV_VARS = [
    "VIDEO_DEV",
    "AUDIO_SRC",
    "VAAPI_DEV",
    "SCHEMA_VERSION",
    "PIPELINE_VERSION",
]

missing = [k for k in REQUIRED_ENV_VARS if not ENV.get(k)]
if missing:
    print(
        f"[privledger] ERROR: missing required env vars: {', '.join(missing)}",
        file=sys.stderr,
    )
    sys.exit(1)

###############################################################################
# Schema
###############################################################################

if not SCHEMA_PATH.exists():
    print("[privledger] ERROR: schema file missing", file=sys.stderr)
    sys.exit(1)

SCHEMA = json.loads(SCHEMA_PATH.read_text())

###############################################################################
# Process supervision
###############################################################################

proc: subprocess.Popen | None = None


def handle_signal(signum, frame):
    # SIGTERM is intentionally mapped to the same graceful shutdown path as SIGINT.
    # ffmpeg shutdown is driven via stdin 'q' (through record.sh), not by signal type.
    # Uniform graceful teardown is preferred over preserving original signal semantics.
    if proc and proc.poll() is None:
        print("[privledger] Forwarding SIGINT to recorder…", flush=True)
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGINT)
        except ProcessLookupError:
            pass


def main():
    global proc

    if not RECORD_SCRIPT.exists():
        print("[privledger] ERROR: record.sh not found", file=sys.stderr)
        sys.exit(1)

    ###########################################################################
    # Timestamp — Python is authoritative, passed down to record.sh
    ###########################################################################

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d-%H%M")
    timestamp_utc_iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp_local_iso = now.astimezone().replace(microsecond=0).isoformat()
    ENV["TIMESTAMP"] = timestamp

    print(f"[privledger] Starting capture at {timestamp}…", flush=True)

    try:
        proc = subprocess.Popen(
            [str(RECORD_SCRIPT)],
            env=ENV,
            start_new_session=True,
        )

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        exit_code = proc.wait()

    except KeyboardInterrupt:
        # Fallback safety; normally handled by signal handler
        handle_signal(signal.SIGINT, None)
        exit_code = proc.wait()

    ###########################################################################
    # Three-way filesystem check — filesystem is authoritative, not exit code
    ###########################################################################

    good_path = ROOT_DIR / "vlog" / f"{timestamp}.mkv"
    bad_path  = ROOT_DIR / "vlog" / f"{timestamp}.mkv.bad.mkv"

    good_exists = good_path.exists()
    bad_exists  = bad_path.exists()

    # Invariant violation — both states cannot coexist
    if good_exists and bad_exists:
        print(
            "[privledger] FATAL: both good and bad artifacts exist — pipeline invariant violated",
            file=sys.stderr,
        )
        sys.exit(2)

    # Case C: preflight or early failure — no artifact produced
    if not good_exists and not bad_exists:
        print(
            f"[privledger] ERROR: no media artifact found for {timestamp} — preflight or early failure",
            file=sys.stderr,
        )
        sys.exit(exit_code if exit_code != 0 else 1)

    # Resolve media file and quality
    if good_exists:
        media_file       = good_path.name
        metadata_quality = "basic"
    else:
        media_file       = bad_path.name
        metadata_quality = "bad"

    ###########################################################################
    # Metadata write
    ###########################################################################

    metadata_path = ROOT_DIR / "vlog" / f"{timestamp}.json"

    try:
        written = write_metadata_atomic(
            output_path=metadata_path,
            entry_id=timestamp,
            timestamp_utc=timestamp_utc_iso,
            media_file=media_file,
            metadata_quality=metadata_quality,
            schema_version=int(SCHEMA_VERSION),
            pipeline_version=PIPELINE_VERSION,
            optional_fields={"timestamp_local": timestamp_local_iso},
            schema=SCHEMA,
        )
        print(f"[privledger] Metadata written → {written.name}", flush=True)
    except Exception as e:
        print(f"[privledger] ERROR: metadata write failed: {e}", file=sys.stderr)
        sys.exit(1)

    if exit_code != 0:
        print(
            f"[privledger] Capture finished with bad artifact (exit {exit_code})",
            file=sys.stderr,
        )
        sys.exit(exit_code)

    print("[privledger] Capture finished cleanly.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
