#!/usr/bin/env python3

import os
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

###############################################################################
# Paths and environment
###############################################################################

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_ENV = ROOT_DIR / "config" / "env"
RECORD_SCRIPT = ROOT_DIR / "scripts" / "record.sh"

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
# Device configuration (authoritative here)
###############################################################################

ENV = os.environ.copy()
ENV.update(
    {
        "VIDEO_DEV": "/dev/v4l/by-id/usb-046d_Brio_100_2525APJ56A18-video-index0",
        "AUDIO_SRC": "alsa_input.usb-046d_Brio_100_2525APJ56A18-02.mono-fallback",
        "VAAPI_DEV": "/dev/dri/renderD128",
    }
)

###############################################################################
# Process supervision
###############################################################################

proc: subprocess.Popen | None = None


def handle_signal(signum, frame):
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

    print("[privledger] Starting capture…", flush=True)

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

    if exit_code != 0:
        print(f"[privledger] Recorder exited with code {exit_code}", file=sys.stderr)
        sys.exit(exit_code)

    print("[privledger] Capture finished cleanly.", flush=True)
    sys.exit(0)


if __name__ == "__main__":
    main()
