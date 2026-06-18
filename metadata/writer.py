import json
import os
import tempfile
from pathlib import Path

from metadata.check import check_core_invariants
from metadata.validator import validate_metadata


def write_json_atomic(output_path: Path, payload_obj: dict) -> Path:
    """Serialize a dict canonically and atomically replace output_path."""
    payload = (
        json.dumps(
            payload_obj,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")

    output_path = Path(output_path)
    parent = output_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=f".tmp.{os.getpid()}")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        dir_fd = os.open(str(parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        os.replace(tmp_path, output_path)

    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    return output_path


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

    # Enforce core invariants before schema validation.
    check_core_invariants(metadata)

    # 2. Validate against schema — fail fast, nothing written if invalid
    validate_metadata(metadata, schema)

    return write_json_atomic(output_path, metadata)
