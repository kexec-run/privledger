import json

import pytest

from metadata.check import check_core_invariants
from metadata.writer import write_metadata_atomic


MOCK_SCHEMA = {
    "type": "object",
    "required": [
        "id",
        "timestamp_utc",
        "schema_version",
        "pipeline_version",
        "metadata_quality",
        "media_file",
    ],
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "timestamp_utc": {"type": "string"},
        "timestamp_local": {"type": ["string", "null"]},
        "schema_version": {"type": "integer"},
        "pipeline_version": {"type": "string", "minLength": 1},
        "metadata_quality": {
            "type": "string",
            "enum": ["basic", "full", "corrected", "bad"],
        },
        "media_file": {"type": "string", "minLength": 1},
        "video_device": {"type": ["string", "null"], "minLength": 1},
        "transcript_file": {
            "oneOf": [
                {"type": "null"},
                {"type": "string", "minLength": 1},
            ]
        },
        "mood": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
        "energy": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
        "stress": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
        "sleepiness": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
        "sleep_hours": {"type": ["number", "null"], "minimum": 0},
        "caffeine_mg": {"type": ["number", "null"], "minimum": 0},
        "body_weight": {"type": ["number", "null"], "minimum": 0},
        "focus_domain": {"type": ["string", "null"]},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
            "maxItems": 5,
        },
        "location": {"type": ["string", "null"]},
        "custom": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "schema_hash": {"type": "string"},
                "data": {"type": "object"},
            },
            "required": ["schema_hash", "data"],
        },
    },
}


def write_entry(tmp_path, *, optional_fields=None, metadata_quality="basic"):
    output_path = tmp_path / "2026-05-24-1200.json"
    written = write_metadata_atomic(
        output_path=output_path,
        entry_id="2026-05-24-1200",
        timestamp_utc="2026-05-24T06:30:00Z",
        media_file="2026-05-24-1200.mkv",
        metadata_quality=metadata_quality,
        schema_version=1,
        pipeline_version="0.1.0",
        optional_fields=optional_fields,
        schema=MOCK_SCHEMA,
    )
    return written, json.loads(output_path.read_text())


class TestCoreInvariants:
    def test_focus_domain_can_be_null_without_tags(self):
        data = {"tags": [], "focus_domain": None}

        check_core_invariants(data)

    def test_focus_domain_can_be_vocab_tag_without_regular_tag_duplication(self):
        data = {"tags": ["chores"], "focus_domain": "sleep"}

        check_core_invariants(data)

    def test_focus_domain_must_exist_in_tag_vocabulary(self):
        with pytest.raises(
            ValueError,
            match="focus_domain must be null or exist in configured tag vocabulary",
        ):
            check_core_invariants({"tags": ["programming"], "focus_domain": "notatag"})

    def test_focus_domain_can_be_vocab_tag_when_tags_empty(self):
        check_core_invariants({"tags": [], "focus_domain": "programming"})

    def test_focus_domain_must_not_be_duplicated_in_regular_tags(self):
        with pytest.raises(
            ValueError,
            match="focus_domain must not be duplicated in regular tags",
        ):
            check_core_invariants({"tags": ["sleep"], "focus_domain": "sleep"})

    def test_tags_none_normalizes_to_empty_list(self):
        data = {"tags": None, "focus_domain": None}

        check_core_invariants(data)

        assert data["tags"] == []

    def test_tags_must_be_list(self):
        with pytest.raises(TypeError, match="tags must be a list"):
            check_core_invariants({"tags": "programming", "focus_domain": None})

    def test_tags_must_contain_strings(self):
        with pytest.raises(TypeError, match="tags must contain strings"):
            check_core_invariants({"tags": [1], "focus_domain": None})

    def test_tags_must_be_lowercase(self):
        with pytest.raises(ValueError, match="tags must be lowercase"):
            check_core_invariants({"tags": ["Programming"], "focus_domain": None})


class TestWriterWithMockSchema:
    def test_minimal_metadata_write_succeeds(self, tmp_path):
        written, data = write_entry(tmp_path)

        assert written.exists()
        assert data["id"] == "2026-05-24-1200"
        assert data["metadata_quality"] == "basic"
        assert data["tags"] == []
        assert data["focus_domain"] is None

    def test_focus_domain_without_regular_tag_duplication_succeeds(self, tmp_path):
        _, data = write_entry(
            tmp_path,
            optional_fields={
                "tags": ["chores"],
                "focus_domain": "sleep",
            },
        )

        assert data["focus_domain"] == "sleep"
        assert data["tags"] == ["chores"]

    def test_tags_none_succeeds_as_empty_list(self, tmp_path):
        _, data = write_entry(tmp_path, optional_fields={"tags": None})

        assert data["tags"] == []

    def test_optional_fields_must_be_dict(self, tmp_path):
        output_path = tmp_path / "2026-05-24-1200.json"

        with pytest.raises(TypeError, match="optional_fields must be a dict or None"):
            write_metadata_atomic(
                output_path=output_path,
                entry_id="2026-05-24-1200",
                timestamp_utc="2026-05-24T06:30:00Z",
                media_file="2026-05-24-1200.mkv",
                metadata_quality="basic",
                schema_version=1,
                pipeline_version="0.1.0",
                optional_fields=["tags"],  # pyright: ignore[reportArgumentType]
                schema=MOCK_SCHEMA,
            )

        assert not output_path.exists()

    @pytest.mark.parametrize(
        "optional_fields, match",
        [
            (
                {"tags": ["programming"], "focus_domain": "notatag"},
                "focus_domain must be null or exist in configured tag vocabulary",
            ),
            (
                {"tags": ["notatag"]},
                "tags must exist in configured tag vocabulary",
            ),
            (
                {"tags": ["sleep"], "focus_domain": "sleep"},
                "focus_domain must not be duplicated in regular tags",
            ),
            ({"tags": "programming"}, "tags must be a list"),
            ({"tags": [1]}, "tags must contain strings"),
            ({"tags": ["Programming"]}, "tags must be lowercase"),
            ({"tags": ["programming", "programming"]}, "non-unique elements"),
            (
                {
                    "tags": [
                        "programming",
                        "fatigue",
                        "sleep",
                        "exercise",
                        "planning",
                        "systems",
                    ]
                },
                "is too long",
            ),
            ({"mood": 6}, "greater than the maximum"),
            ({"sleep_hours": -1}, "less than the minimum"),
            ({"unknown_field": "x"}, "Additional properties are not allowed"),
        ],
    )
    def test_invariant_failure_does_not_write_file(
        self, tmp_path, optional_fields, match
    ):
        output_path = tmp_path / "2026-05-24-1200.json"

        with pytest.raises(Exception, match=match):
            write_metadata_atomic(
                output_path=output_path,
                entry_id="2026-05-24-1200",
                timestamp_utc="2026-05-24T06:30:00Z",
                media_file="2026-05-24-1200.mkv",
                metadata_quality="basic",
                schema_version=1,
                pipeline_version="0.1.0",
                optional_fields=optional_fields,
                schema=MOCK_SCHEMA,
            )

        assert not output_path.exists()

    def test_metadata_quality_must_be_known_value(self, tmp_path):
        output_path = tmp_path / "2026-05-24-1200.json"

        with pytest.raises(Exception, match="is not one of"):
            write_metadata_atomic(
                output_path=output_path,
                entry_id="2026-05-24-1200",
                timestamp_utc="2026-05-24T06:30:00Z",
                media_file="2026-05-24-1200.mkv",
                metadata_quality="partial",
                schema_version=1,
                pipeline_version="0.1.0",
                optional_fields=None,
                schema=MOCK_SCHEMA,
            )

        assert not output_path.exists()
