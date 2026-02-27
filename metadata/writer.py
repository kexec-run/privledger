import json
import os
import tempfile
from pathlib import Path

from metadata.validator import validate_metadata


def write_metadata_atomic(
    *,
    output_path: Path,
    entry_id: str,
    timestamp_utc: str,
    media_file: str,
    metadata_quality: str,
    schema_version: int,
    pipeline_version: str,
    optional_fields: dict | None,
    schema: dict,
) -> Path:
    """
    Build, validate, and atomically write a metadata JSON file.

    Returns the final written Path.
    Raises on any failure. Nothing is written if validation fails.
    """

    # 1. Build metadata object
    metadata = {
        "id": entry_id,
        "timestamp_utc": timestamp_utc,
        "schema_version": schema_version,
        "pipeline_version": pipeline_version,
        "metadata_quality": metadata_quality,
        "media_file": media_file,
        "mood": None,
        "energy": None,
        "stress": None,
        "sleepiness": None,
        "sleep_hours": None,
        "caffeine_mg": None,
        "body_weight": None,
        "focus_domain": None,
        "location": None,
        "tags": [],
        "timestamp_local": None,
        "transcript_file": None,
    }

    if optional_fields is not None:
        if not isinstance(optional_fields, dict):
            raise TypeError("optional_fields must be a dict or None")
        metadata.update(optional_fields)

    # Enforce tags invariant — must always be a list
    if metadata.get("tags") is None:
        metadata["tags"] = []
    if not isinstance(metadata["tags"], list):
        raise TypeError("tags must be a list")

    # 2. Validate against schema — fail fast, nothing written if invalid
    validate_metadata(metadata, schema)

    # 3. Canonical JSON serialization
    payload = (
        json.dumps(
            metadata,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")

    # 4. Atomic write: temp → flush → fsync file → fsync dir → rename
    output_path = Path(output_path)
    parent = output_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=f".tmp.{os.getpid()}")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        # fsync the directory
        dir_fd = os.open(str(parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        os.replace(tmp_path, output_path)

    except Exception:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return output_path
