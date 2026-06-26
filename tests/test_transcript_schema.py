import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from tests.test_transcript_batch import (
    valid_transcript,
    valid_translation,
    write_source,
)


SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "transcript.v1.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_text())
TRANSLATION_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "translation.v1.schema.json"
)
TRANSLATION_SCHEMA = json.loads(TRANSLATION_SCHEMA_PATH.read_text())


def test_transcript_schema_is_valid_and_accepts_observed_shape():
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA).validate(valid_transcript())


def test_transcript_schema_requires_segment_text():
    payload = valid_transcript()
    del payload["transcription"][0]["text"]

    with pytest.raises(ValidationError, match="'text' is a required property"):
        Draft202012Validator(SCHEMA).validate(payload)


def test_translation_schema_is_valid_and_accepts_generated_shape(tmp_path):
    source = tmp_path / "TS.whisper-large-v3-source.json"
    write_source(source)

    Draft202012Validator.check_schema(TRANSLATION_SCHEMA)
    Draft202012Validator(TRANSLATION_SCHEMA).validate(valid_translation(source))
