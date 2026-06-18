import json

import pytest

from metadata.rewrite import rewrite_existing_metadata_atomic
from tests.test_writer_invariants import MOCK_SCHEMA


def base_metadata():
    return {
        "id": "2026-05-24-0630",
        "timestamp_utc": "2026-05-24T06:30:00Z",
        "timestamp_local": "2026-05-24T12:00:00+05:30",
        "schema_version": 1,
        "pipeline_version": "0.1.0",
        "metadata_quality": "basic",
        "media_file": "2026-05-24-0630.mkv",
        "video_device": "mock camera",
        "transcript_file": None,
        "mood": None,
        "energy": None,
        "stress": None,
        "sleepiness": None,
        "sleep_hours": None,
        "caffeine_mg": None,
        "body_weight": None,
        "focus_domain": None,
        "tags": [],
        "location": None,
    }


def test_rewrite_preserves_capture_fields_and_updates_allowed_fields(tmp_path):
    original = base_metadata()
    output_path = tmp_path / "2026-05-24-0630.json"

    rewrite_existing_metadata_atomic(
        output_path=output_path,
        original=original,
        updates={
            "transcript_file": "transcripts/2026-05-24-0630.whisper-large-v3.json",
            "metadata_quality": "full",
        },
        allowed_updates={"transcript_file", "metadata_quality"},
        schema=MOCK_SCHEMA,
    )

    updated = json.loads(output_path.read_text())
    assert updated["id"] == original["id"]
    assert updated["timestamp_utc"] == original["timestamp_utc"]
    assert updated["media_file"] == original["media_file"]
    assert updated["video_device"] == original["video_device"]
    assert updated["metadata_quality"] == "full"
    assert (
        updated["transcript_file"]
        == "transcripts/2026-05-24-0630.whisper-large-v3.json"
    )


def test_rewrite_rejects_disallowed_updates(tmp_path):
    with pytest.raises(ValueError, match="disallowed metadata updates"):
        rewrite_existing_metadata_atomic(
            output_path=tmp_path / "2026-05-24-0630.json",
            original=base_metadata(),
            updates={"media_file": "other.mkv"},
            allowed_updates={"transcript_file"},
            schema=MOCK_SCHEMA,
        )


def test_rewrite_validates_before_replacing_existing_file(tmp_path):
    output_path = tmp_path / "2026-05-24-0630.json"
    output_path.write_text('{"unchanged":true}\n')

    with pytest.raises(Exception, match="is not one of"):
        rewrite_existing_metadata_atomic(
            output_path=output_path,
            original=base_metadata(),
            updates={"metadata_quality": "partial"},
            allowed_updates={"metadata_quality"},
            schema=MOCK_SCHEMA,
        )

    assert json.loads(output_path.read_text()) == {"unchanged": True}
