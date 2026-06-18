from pathlib import Path
from typing import Final

from metadata.check import check_core_invariants, check_invariants
from metadata.validator import validate_metadata
from metadata.writer import write_json_atomic, write_metadata_atomic


CORE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "timestamp_utc",
        "schema_version",
        "pipeline_version",
        "metadata_quality",
        "media_file",
    }
)

_SKIP_CUSTOM_INVARIANTS = object()


def rewrite_existing_metadata_atomic(
    *,
    output_path: Path,
    original: dict,
    updates: dict,
    allowed_updates: set[str] | frozenset[str],
    schema: dict,
    schema_version: int | None = None,
    pipeline_version: str | None = None,
    custom_fields=_SKIP_CUSTOM_INVARIANTS,
    custom_types=None,
    current_hash=None,
) -> Path:
    """Merge allowed updates into existing metadata and write atomically."""
    validate_existing_metadata_update(
        original=original,
        updates=updates,
        allowed_updates=allowed_updates,
        schema=schema,
        custom_fields=custom_fields,
        custom_types=custom_types,
        current_hash=current_hash,
    )
    merged = {**original, **updates}

    return write_metadata_atomic(
        output_path=output_path,
        entry_id=merged["id"],
        timestamp_utc=merged["timestamp_utc"],
        media_file=merged["media_file"],
        metadata_quality=merged["metadata_quality"],
        schema_version=int(
            merged["schema_version"] if schema_version is None else schema_version
        ),
        pipeline_version=(
            merged["pipeline_version"] if pipeline_version is None else pipeline_version
        ),
        optional_fields={k: v for k, v in merged.items() if k not in CORE_FIELDS},
        schema=schema,
    )


def validate_existing_metadata_update(
    *,
    original: dict,
    updates: dict,
    allowed_updates: set[str] | frozenset[str],
    schema: dict,
    custom_fields=_SKIP_CUSTOM_INVARIANTS,
    custom_types=None,
    current_hash=None,
) -> dict:
    """Validate an allowed metadata update without writing it."""
    if not isinstance(original, dict):
        raise TypeError("original must be a dict")
    if not isinstance(updates, dict):
        raise TypeError("updates must be a dict")

    disallowed = set(updates) - set(allowed_updates)
    if disallowed:
        raise ValueError(f"disallowed metadata updates: {sorted(disallowed)}")

    merged = {**original, **updates}

    check_core_invariants(merged)
    validate_metadata(merged, schema)

    if custom_fields is not _SKIP_CUSTOM_INVARIANTS:
        check_invariants(merged, custom_fields, custom_types, current_hash)

    return merged


def patch_existing_metadata_atomic(
    *,
    output_path: Path,
    original: dict,
    updates: dict,
    allowed_updates: set[str] | frozenset[str],
) -> Path:
    """Atomically patch selected fields without validating unrelated metadata."""
    if not isinstance(original, dict):
        raise TypeError("original must be a dict")
    if not isinstance(updates, dict):
        raise TypeError("updates must be a dict")

    disallowed = set(updates) - set(allowed_updates)
    if disallowed:
        raise ValueError(f"disallowed metadata updates: {sorted(disallowed)}")

    return write_json_atomic(output_path, {**original, **updates})
