#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from metadata.check import check_invariants  # noqa: E402
from metadata.writer import write_metadata_atomic  # noqa: E402

###############################################################################
# Paths and environment
###############################################################################

CONFIG_ENV = ROOT_DIR / "config" / "env"
SCHEMA_PATH = ROOT_DIR / "tests" / "schema" / "metadata.v1.schema.json"
VLOG_DIR = ROOT_DIR / "vlog"

if not CONFIG_ENV.exists():
    print(
        "[enrich] ERROR: config/env missing (copy from config/env.sample)",
        file=sys.stderr,
    )
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

_MISSING = object()

###############################################################################
# Custom schema (optional)
###############################################################################

CUSTOM_SCHEMA_PATH = ROOT_DIR / "config" / "custom_schema.yaml"
CUSTOM_ENABLED = os.getenv("CUSTOM_ENABLED", "false").lower() == "true"

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
    print("Tags (append, comma separated)")
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
# Custom schema functions
###############################################################################


def prompt_bool(label: str, current):
    """Prompt for a boolean (y/n). Enter = keep current."""
    display = "y" if current is True else "n" if current is False else ""
    while True:
        raw = _readline(f"{label} (y/n) [current: {display}] ").lower()
        if not raw:
            return current
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  Invalid. Enter y/n or blank.")


def prompt_for_type(label, typ, current):
    """Type-driven prompt dispatcher."""
    if typ is int:
        return prompt_int(label, current, 0, 10**9)
    elif typ == (int, float):
        return prompt_float(label, current)
    elif typ is bool:
        return prompt_bool(label, current)
    elif typ is str:
        return prompt_str(label, current)
    else:
        raise ValueError(f"unsupported type for {label}")


def prompt_schema_change(old, new):
    """Prompt user when schema hash changed."""
    print(f"Schema changed ({old} → {new})")
    raw = _readline("1. Keep existing  2. Overwrite: ")
    return "keep" if raw == "1" else "overwrite"


def build_custom(fields, types, schema_hash):
    """Build fresh custom envelope with prompted values."""
    data = {}
    for f in fields:
        data[f] = prompt_for_type(f, types[f], None)
    return {"schema_hash": schema_hash, "data": data}


def update_existing(custom, fields, types):
    """Update existing custom envelope, preserving current values."""
    data = {}
    for f in fields:
        current = custom["data"].get(f)
        data[f] = prompt_for_type(f, types[f], current)
    return {"schema_hash": custom["schema_hash"], "data": data}


def resolve_custom(original, fields, types, current_hash):
    """Resolve next custom state from (original, YAML)."""
    custom = original.get("custom", _MISSING)

    if fields is None:
        return _MISSING  # feature disabled

    if custom is _MISSING:
        return None  # not enriched yet

    if custom is None:
        return build_custom(fields, types, current_hash)  # first enrichment

    old_hash = custom["schema_hash"]

    if old_hash == current_hash:
        return update_existing(custom, fields, types)  # same schema

    decision = prompt_schema_change(old_hash, current_hash)
    if decision == "keep":
        return custom
    return build_custom(fields, types, current_hash)


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
    print("  Enrich Metadata")
    print(f"  Session: {ts}")
    print(f"{'─' * 40}\n")

    # Immutable fields — passed through unchanged
    IMMUTABLE = {
        "id",
        "timestamp_utc",
        "timestamp_local",
        "schema_version",
        "pipeline_version",
        "media_file",
        "video_device",
        "metadata_quality",
        "transcript_file",
        "custom",
    }

    # Load custom schema if enabled
    fields = types = current_hash = None
    new_custom = _MISSING
    if CUSTOM_ENABLED:
        try:
            from metadata.custom_schema import load_custom_schema

            fields, types, current_hash = load_custom_schema(CUSTOM_SCHEMA_PATH)
        except FileNotFoundError:
            pass  # YAML missing — skip custom processing

    try:
        updates = {}
        updates["mood"] = prompt_int("Mood", original.get("mood"), 1, 5)
        updates["energy"] = prompt_int("Energy", original.get("energy"), 1, 5)
        updates["stress"] = prompt_int("Stress", original.get("stress"), 1, 5)
        updates["sleepiness"] = prompt_int(
            "Sleepiness", original.get("sleepiness"), 1, 5
        )
        updates["sleep_hours"] = prompt_float(
            "Sleep hours", original.get("sleep_hours")
        )
        updates["caffeine_mg"] = prompt_float(
            "Caffeine mg", original.get("caffeine_mg")
        )
        updates["body_weight"] = prompt_float(
            "Body weight", original.get("body_weight")
        )
        updates["focus_domain"] = prompt_str(
            "Focus domain", original.get("focus_domain")
        )
        updates["tags"] = prompt_tags(original.get("tags") or [])
        updates["location"] = prompt_str("Location", original.get("location"))

        # Custom schema transform
        new_custom = resolve_custom(original, fields, types, current_hash)
    except KeyboardInterrupt:
        print("\n\n[enrich] Aborted. No changes written.")
        sys.exit(0)

    print()

    # Strip any accidental immutable field overwrites before merge
    for k in IMMUTABLE:
        updates.pop(k, None)

    # Merge: immutable fields from original, user fields from updates
    merged = {**original, **updates}
    if new_custom is _MISSING:
        merged.pop("custom", None)
    else:
        merged["custom"] = new_custom

    # Validate invariants before write
    try:
        check_invariants(merged, fields, types, current_hash)
    except ValueError as e:
        print(f"[enrich] ERROR: validation failed: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        write_metadata_atomic(
            output_path=meta_path,
            entry_id=merged["id"],
            timestamp_utc=merged["timestamp_utc"],
            media_file=merged["media_file"],
            metadata_quality=merged["metadata_quality"],
            schema_version=int(SCHEMA_VERSION),
            pipeline_version=PIPELINE_VERSION,
            optional_fields={
                k: v
                for k, v in merged.items()
                if k
                not in {
                    "id",
                    "timestamp_utc",
                    "schema_version",
                    "pipeline_version",
                    "metadata_quality",
                    "media_file",
                }
            },
            schema=SCHEMA,
        )
        print(f"[enrich] Metadata updated → {meta_path.name}")
    except Exception as e:
        print(f"[enrich] ERROR: write failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
