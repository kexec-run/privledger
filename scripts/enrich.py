#!/usr/bin/env python3

import json
import os
import importlib
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from metadata.rewrite import rewrite_existing_metadata_atomic  # noqa: E402
from metadata.tags import load_tag_vocabulary, validate_focus_domain  # noqa: E402

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

ENRICH_ALLOWED_UPDATES = frozenset(
    {
        "mood",
        "energy",
        "stress",
        "sleepiness",
        "sleep_hours",
        "caffeine_mg",
        "body_weight",
        "focus_domain",
        "tags",
        "location",
        "custom",
    }
)

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


def print_tag_grid(tags: list[str], *, columns: int = 4) -> None:
    """Print tags horizontally for quick scanning."""
    if not tags:
        return

    width = max(len(tag) for tag in tags) + 4
    for i in range(0, len(tags), columns):
        row = tags[i : i + columns]
        print("".join(f"{tag:<{width}}" for tag in row).rstrip())


def tag_match_score(query: str, candidate: str) -> int:
    """Score a raw tag query against a canonical tag."""
    normalized = query.strip().lower()
    if normalized == candidate:
        return 100

    try:
        fuzz = importlib.import_module("rapidfuzz.fuzz")
        return int(fuzz.WRatio(normalized, candidate))
    except ImportError:
        from difflib import SequenceMatcher

        return int(SequenceMatcher(None, normalized, candidate).ratio() * 100)


def tag_candidates(
    raw: str, vocabulary: list[str], *, min_score: int = 75
) -> list[str]:
    """Return canonical tag candidates ordered by typo-match score."""
    query = raw.strip().lower()
    scored = [
        (tag_match_score(query, tag), tag)
        for tag in vocabulary
        if tag_match_score(query, tag) >= min_score
    ]
    return [tag for _score, tag in sorted(scored, key=lambda item: (-item[0], item[1]))]


def choose_candidate(raw: str, candidates: list[str]) -> str:
    """Choose one canonical tag from multiple plausible candidates."""
    print(f"Did you mean '{raw}'?")
    for i, tag in enumerate(candidates, start=1):
        print(f"{i}. {tag}  score {tag_match_score(raw, tag)}")

    while True:
        choice = _readline("Select: ")
        try:
            index = int(choice)
        except ValueError:
            print("  Invalid. Enter a number.")
            continue
        if 1 <= index <= len(candidates):
            selected = candidates[index - 1]
            if selected != raw:
                print(f'Resolved "{raw}" -> {selected}')
            return selected
        print(f"  Invalid. Enter 1-{len(candidates)}.")


def resolve_tag_input(raw: str, vocabulary: list[str]) -> str:
    """Resolve raw user input to exactly one canonical tag."""
    normalized = raw.strip().lower()
    if not normalized:
        raise ValueError("empty tag")

    if not vocabulary:
        return normalized
    if normalized in vocabulary:
        return normalized

    candidates = tag_candidates(normalized, vocabulary)
    if not candidates:
        raise ValueError(f"unknown tag: {normalized}")
    if len(candidates) == 1:
        selected = candidates[0]
        print(f'Resolved "{normalized}" -> {selected}')
        return selected
    return choose_candidate(normalized, candidates)


def merge_tags(
    existing: list[str],
    selected: list[str],
    vocabulary: list[str],
    focus_domain: str | None = None,
) -> list[str]:
    vocabulary_set = set(vocabulary)
    merged = list(existing)

    for tag in selected:
        normalized = resolve_tag_input(tag, vocabulary)
        if not normalized:
            continue
        if vocabulary_set and normalized not in vocabulary_set:
            raise ValueError(f"unknown tag: {normalized}")
        if normalized not in merged:
            merged.append(normalized)

    validate_focus_domain(focus_domain, merged, vocabulary_set)

    if len(merged) > 5:
        raise ValueError("tag limit is 5")

    return sorted(merged)


def prompt_tags(
    existing: list[str],
    vocabulary: list[str] | None = None,
    focus_domain: str | None = None,
) -> list[str]:
    """Prompt for tags to append. Enter = no change."""
    vocabulary = vocabulary if vocabulary is not None else load_tag_vocabulary()

    while True:
        display = ", ".join(existing) if existing else "none"
        print()
        print(f"Selected tags: {display}")

        raw = _readline("Additional tags (comma separated, optional): ")
        if not raw:
            return existing

        selected = [t.strip() for t in raw.split(",") if t.strip()]
        try:
            return merge_tags(existing, selected, vocabulary, focus_domain)
        except ValueError as e:
            print(f"  Invalid tags: {e}")


def prompt_focus_domain(
    current: str | None,
    vocabulary: list[str],
    regular_tags: list[str],
) -> str | None:
    """Select one primary tag as focus domain. Enter = keep current when valid."""
    if current is not None and vocabulary and current not in vocabulary:
        current = None
    vocabulary_set = set(vocabulary)

    while True:
        display = current if current is not None else ""
        raw = _readline(
            f"Focus domain (select only one primary tag) [current: {display}]: "
        )
        if not raw and current is None:
            return None
        try:
            selected = current if not raw else resolve_tag_input(raw, vocabulary)
            validate_focus_domain(selected, regular_tags, vocabulary_set)
            return selected
        except ValueError as e:
            print(f"  Invalid focus domain: {e}")


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
        print("Ratings")
        updates["mood"] = prompt_int("Mood", original.get("mood"), 1, 5)
        updates["energy"] = prompt_int("Energy", original.get("energy"), 1, 5)
        updates["stress"] = prompt_int("Stress", original.get("stress"), 1, 5)
        updates["sleepiness"] = prompt_int(
            "Sleepiness", original.get("sleepiness"), 1, 5
        )

        print()
        print("Body")
        updates["sleep_hours"] = prompt_float(
            "Sleep hours", original.get("sleep_hours")
        )
        updates["caffeine_mg"] = prompt_float(
            "Caffeine mg", original.get("caffeine_mg")
        )
        updates["body_weight"] = prompt_float(
            "Body weight", original.get("body_weight")
        )
        print()
        print("Tags")
        print("Available:")
        tag_vocabulary = load_tag_vocabulary()
        print_tag_grid(tag_vocabulary)
        print()
        existing_tags = original.get("tags") or []
        updates["focus_domain"] = prompt_focus_domain(
            original.get("focus_domain"), tag_vocabulary, existing_tags
        )
        updates["tags"] = prompt_tags(
            existing_tags,
            tag_vocabulary,
            updates["focus_domain"],
        )

        print()
        updates["location"] = prompt_str("Location", original.get("location"))

        # Custom schema transform
        new_custom = resolve_custom(original, fields, types, current_hash)
    except KeyboardInterrupt:
        print("\n\n[enrich] Aborted. No changes written.")
        sys.exit(0)
    except ValueError as e:
        print(f"[enrich] ERROR: validation failed: {e}", file=sys.stderr)
        sys.exit(1)

    print()

    if new_custom is _MISSING:
        updates.pop("custom", None)
    else:
        updates["custom"] = new_custom

    try:
        rewrite_existing_metadata_atomic(
            output_path=meta_path,
            original=original,
            updates=updates,
            allowed_updates=ENRICH_ALLOWED_UPDATES,
            schema_version=int(SCHEMA_VERSION),
            pipeline_version=PIPELINE_VERSION,
            schema=SCHEMA,
            custom_fields=fields,
            custom_types=types,
            current_hash=current_hash,
        )
        print(f"[enrich] Metadata updated → {meta_path.name}")
    except ValueError as e:
        print(f"[enrich] ERROR: validation failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[enrich] ERROR: write failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
