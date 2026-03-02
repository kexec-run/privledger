#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from metadata.writer import write_metadata_atomic

###############################################################################
# Paths and environment
###############################################################################

CONFIG_ENV = ROOT_DIR / "config" / "env"
SCHEMA_PATH = ROOT_DIR / "tests" / "schema" / "metadata.v1.schema.json"
VLOG_DIR = ROOT_DIR / "vlog"

if not CONFIG_ENV.exists():
    print("[enrich] ERROR: config/env missing", file=sys.stderr)
    sys.exit(1)

load_dotenv(CONFIG_ENV)

SCHEMA_VERSION = os.getenv("SCHEMA_VERSION")
PIPELINE_VERSION = os.getenv("PIPELINE_VERSION")

if not SCHEMA_VERSION or not PIPELINE_VERSION:
    print("[enrich] ERROR: missing required env values", file=sys.stderr)
    sys.exit(1)

if not SCHEMA_PATH.exists():
    print("[enrich] ERROR: schema file missing", file=sys.stderr)
    sys.exit(1)

SCHEMA = json.loads(SCHEMA_PATH.read_text())

###############################################################################
# Resolution helpers
###############################################################################

def resolve_timestamp(input_path: str) -> str:
    """Extract timestamp from any accepted input form."""
    name = Path(input_path).name
    # Strip known suffixes
    for suffix in (".mkv.bad.mkv", ".mkv", ".json"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def resolve_metadata_path(ts: str) -> Path:
    return VLOG_DIR / f"{ts}.json"


def load_metadata(path: Path) -> dict:
    return json.loads(path.read_text())


###############################################################################
# Input normalization
###############################################################################

def _readline(prompt: str) -> str:
    """Read a line using sys.stdin.readline to bypass TTY CR artifacts."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    try:
        s = sys.stdin.readline()
    except EOFError:
        return ""
    return s.replace("\r", "").replace("\n", "").strip()


###############################################################################
# Prompt helpers
###############################################################################

def prompt_int(label: str, current, min_val: int, max_val: int):
    """Prompt for an integer in [min_val, max_val]. Enter = keep current."""
    display = str(current) if current is not None else ""
    while True:
        raw = _readline(f"{label} ({min_val}–{max_val}) [current: {display}]: ")
        if not raw:
            return current
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(f"  Invalid. Enter {min_val}–{max_val} or blank.")
        except ValueError:
            print(f"  Invalid. Enter {min_val}–{max_val} or blank.")


def prompt_float(label: str, current):
    """Prompt for a non-negative float. Enter = keep current."""
    display = str(current) if current is not None else ""
    while True:
        raw = _readline(f"{label} [current: {display}]: ")
        if not raw:
            return current
        try:
            val = float(raw)
            if val >= 0:
                return val
            print("  Invalid. Enter a non-negative number or blank.")
        except ValueError:
            print("  Invalid. Enter a number or blank.")


def prompt_str(label: str, current):
    """Prompt for a string. Enter = keep current."""
    display = current if current is not None else ""
    raw = _readline(f"{label} [current: {display}]: ")
    if not raw:
        return current
    return raw


def prompt_tags(existing: list) -> list:
    """Prompt for tags to append. Enter = no change."""
    display = ",".join(existing) if existing else ""
    print(f"Tags (append, comma separated)")
    print(f"Current: {display}")
    raw = _readline("Add tags: ")
    if not raw:
        return existing

    new_tags = [t.strip().lower() for t in raw.split(",") if t.strip()]
    merged = existing + [t for t in new_tags if t not in existing]

    if len(merged) > 5:
        print(f"  Tag limit is 5. Keeping first 5: {merged[:5]}")
        merged = merged[:5]

    return sorted(merged)


###############################################################################
# Main
###############################################################################

def main():
    if len(sys.argv) < 2:
        print("Usage: enrich.py <vlog/TS.mkv | vlog/TS.json | TS>", file=sys.stderr)
        sys.exit(1)

    ts = resolve_timestamp(sys.argv[1])
    meta_path = resolve_metadata_path(ts)

    if not meta_path.exists():
        print(f"[enrich] ERROR: metadata not found for {ts}", file=sys.stderr)
        sys.exit(1)

    original = load_metadata(meta_path)

    print(f"\n{'─' * 40}")
    print(f"  Enrich Metadata")
    print(f"  Session: {ts}")
    print(f"{'─' * 40}\n")

    # Immutable fields — passed through unchanged
    IMMUTABLE = {
        "id", "timestamp_utc", "timestamp_local", "schema_version",
        "pipeline_version", "media_file", "video_device", "metadata_quality",
        "transcript_file",
    }

    try:
        updates = {}
        updates["mood"]         = prompt_int("Mood",       original.get("mood"),       1, 5)
        updates["energy"]       = prompt_int("Energy",     original.get("energy"),     1, 5)
        updates["stress"]       = prompt_int("Stress",     original.get("stress"),     1, 5)
        updates["sleepiness"]   = prompt_int("Sleepiness", original.get("sleepiness"), 1, 5)
        updates["sleep_hours"]  = prompt_float("Sleep hours",  original.get("sleep_hours"))
        updates["caffeine_mg"]  = prompt_float("Caffeine mg",  original.get("caffeine_mg"))
        updates["body_weight"]  = prompt_float("Body weight",  original.get("body_weight"))
        updates["focus_domain"] = prompt_str("Focus domain",   original.get("focus_domain"))
        updates["tags"]         = prompt_tags(original.get("tags") or [])
        updates["location"]     = prompt_str("Location",        original.get("location"))
    except KeyboardInterrupt:
        print("\n\n[enrich] Aborted. No changes written.")
        sys.exit(0)

    print()

    # Strip any accidental immutable field overwrites before merge
    for k in IMMUTABLE:
        updates.pop(k, None)

    # Merge: immutable fields from original, user fields from updates
    merged = {**original, **updates}

    try:
        write_metadata_atomic(
            output_path=meta_path,
            entry_id=merged["id"],
            timestamp_utc=merged["timestamp_utc"],
            media_file=merged["media_file"],
            metadata_quality=merged["metadata_quality"],
            schema_version=int(SCHEMA_VERSION),
            pipeline_version=PIPELINE_VERSION,
            optional_fields={k: v for k, v in merged.items() if k not in {
                "id", "timestamp_utc", "schema_version", "pipeline_version",
                "metadata_quality", "media_file",
            }},
            schema=SCHEMA,
        )
        print(f"[enrich] Metadata updated → {meta_path.name}")
    except Exception as e:
        print(f"[enrich] ERROR: write failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
