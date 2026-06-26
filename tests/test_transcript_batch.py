import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.transcript_batch as transcript_batch
from tests.test_enrich_behavior import base_metadata


MODEL_LABEL = "whisper-large-v3-source"
TARGET_LABEL = "whisper-large-v3-translate-en"


def write_metadata(path: Path, data=None):
    payload = base_metadata()
    payload["id"] = path.stem
    payload["media_file"] = f"{path.stem}.mkv"
    if data:
        payload.update(data)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def valid_transcript():
    return {
        "result": {"language": "en"},
        "transcription": [
            {
                "timestamps": {"from": "00:00:00,000", "to": "00:00:01,000"},
                "offsets": {"from": 0, "to": 1000},
                "text": " hello",
            },
            {
                "timestamps": {"from": "00:00:01,000", "to": "00:00:02,000"},
                "offsets": {"from": 1000, "to": 2000},
                "text": " world",
            },
        ],
    }


def write_source(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valid_transcript()) + "\n")


def valid_translation(source: Path):
    source_payload = valid_transcript()
    segments = []
    for segment in source_payload["transcription"]:
        translated = dict(segment)
        translated["source_text"] = segment["text"]
        translated["text"] = f"translated:{segment['text'].strip()}"
        segments.append(translated)
    return {
        "result": {"language": "en", "source_language": "en"},
        "translation": {
            "source_file": source.name,
            "source_sha256": transcript_batch.source_sha256(source),
            "target_language": "en",
        },
        "transcription": segments,
    }


def test_validate_transcript_accepts_observed_shape():
    transcript_batch.validate_transcript_payload(
        valid_transcript(), media_duration_ms=2500
    )


@pytest.mark.parametrize(
    "payload, match",
    [
        ({"transcription": []}, "non-empty list"),
        (
            {"transcription": [{"offsets": {"from": 1000, "to": 1000}}]},
            "non-positive duration",
        ),
        (
            {
                "transcription": [
                    {"offsets": {"from": 0, "to": 2000}},
                    {"offsets": {"from": 1000, "to": 3000}},
                ]
            },
            "overlaps previous segment",
        ),
    ],
)
def test_validate_transcript_rejects_bad_shapes(payload, match):
    with pytest.raises(transcript_batch.TranscriptValidationError, match=match):
        transcript_batch.validate_transcript_payload(payload)


def test_validate_transcript_enforces_schema_fields():
    payload = valid_transcript()
    del payload["transcription"][0]["text"]

    with pytest.raises(
        transcript_batch.TranscriptValidationError,
        match="transcript schema validation failed",
    ):
        transcript_batch.validate_transcript_payload(payload)


def test_run_whisper_uses_source_transcription_mode(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, *, check):
        calls.append(command)
        assert check is True

    monkeypatch.setattr(transcript_batch.subprocess, "run", fake_run)

    result = transcript_batch.run_whisper(
        tmp_path / "audio.wav",
        tmp_path / "out",
        whisper_cli="whisper-cli",
        model=Path("model.bin"),
        threads=10,
    )

    assert result == tmp_path / "out.json"
    assert "-tr" not in calls[0]
    assert "-oj" in calls[0]


def test_run_whisper_uses_translation_mode(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, *, check):
        calls.append(command)
        assert check is True

    monkeypatch.setattr(transcript_batch.subprocess, "run", fake_run)

    transcript_batch.run_whisper(
        tmp_path / "audio.wav",
        tmp_path / "out",
        whisper_cli="whisper-cli",
        model=Path("model.bin"),
        threads=10,
        translate=True,
    )

    assert "-tr" in calls[0]
    assert "-oj" in calls[0]


def test_discover_transcription_candidates_reports_batch_actions(tmp_path):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()

    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")
    write_metadata(vlog_dir / "2026-05-24-0630.json")

    (vlog_dir / "2026-05-24-0700.mov").write_bytes(b"media")

    (vlog_dir / "2026-05-24-0730.mkv.bad.mkv").write_bytes(b"bad")
    write_metadata(
        vlog_dir / "2026-05-24-0730.json",
        {"media_file": "2026-05-24-0730.mkv.bad.mkv", "metadata_quality": "bad"},
    )

    transcript_dir = vlog_dir / "transcripts"
    transcript_dir.mkdir()
    linked = transcript_dir / f"2026-05-24-0800.{MODEL_LABEL}.json"
    linked.write_text(json.dumps(valid_transcript()) + "\n")
    (vlog_dir / "2026-05-24-0800.mkv").write_bytes(b"media")
    write_metadata(
        vlog_dir / "2026-05-24-0800.json",
        {"transcript_file": f"transcripts/2026-05-24-0800.{MODEL_LABEL}.json"},
    )

    actions = {
        candidate.stem: candidate.action
        for candidate in transcript_batch.discover_transcription_candidates(
            vlog_dir, model_label=MODEL_LABEL
        )
    }

    assert actions == {
        "2026-05-24-0630": "transcribe",
        "2026-05-24-0700": "missing_metadata",
        "2026-05-24-0800": "skip_linked",
    }


def test_discover_transcription_candidates_rejects_metadata_identity_mismatch(tmp_path):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")
    write_metadata(
        vlog_dir / "2026-05-24-0630.json",
        {"id": "2026-05-24-9999"},
    )

    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]

    assert candidate.action == "identity_mismatch"


def test_discover_transcription_candidates_rejects_invalid_linked_transcript(tmp_path):
    vlog_dir = tmp_path / "vlog"
    transcript_dir = vlog_dir / "transcripts"
    transcript_dir.mkdir(parents=True)
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")
    transcript_rel = f"transcripts/2026-05-24-0630.{MODEL_LABEL}.json"
    (vlog_dir / transcript_rel).write_text('{"transcription":[]}\n')
    write_metadata(
        vlog_dir / "2026-05-24-0630.json",
        {"transcript_file": transcript_rel},
    )

    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]

    assert candidate.action == "invalid_linked_transcript"


def test_link_existing_validates_media_duration_before_metadata_update(
    monkeypatch, tmp_path
):
    vlog_dir = tmp_path / "vlog"
    transcript_dir = vlog_dir / "transcripts"
    transcript_dir.mkdir(parents=True)
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")
    metadata_path = vlog_dir / "2026-05-24-0630.json"
    original = write_metadata(metadata_path)
    transcript_path = transcript_dir / f"2026-05-24-0630.{MODEL_LABEL}.json"
    transcript_path.write_text(json.dumps(valid_transcript()) + "\n")
    monkeypatch.setattr(
        transcript_batch,
        "media_duration_ms",
        lambda *_args, **_kwargs: 100_000,
    )
    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]

    with pytest.raises(
        transcript_batch.TranscriptValidationError,
        match="differs from media duration",
    ):
        transcript_batch.process_transcription_candidate(
            candidate,
            args=SimpleNamespace(apply=True, ffprobe="ffprobe"),
        )

    assert json.loads(metadata_path.read_text()) == original


def test_link_rechecks_metadata_identity_after_discovery(monkeypatch, tmp_path):
    vlog_dir = tmp_path / "vlog"
    transcript_dir = vlog_dir / "transcripts"
    transcript_dir.mkdir(parents=True)
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")
    metadata_path = vlog_dir / "2026-05-24-0630.json"
    write_metadata(metadata_path)
    transcript_path = transcript_dir / f"2026-05-24-0630.{MODEL_LABEL}.json"
    transcript_path.write_text(json.dumps(valid_transcript()) + "\n")
    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]
    changed = json.loads(metadata_path.read_text())
    changed["id"] = "different-recording"
    metadata_path.write_text(json.dumps(changed) + "\n")
    monkeypatch.setattr(
        transcript_batch,
        "media_duration_ms",
        lambda *_args, **_kwargs: 2_500,
    )

    with pytest.raises(ValueError, match="metadata id does not match"):
        transcript_batch.process_transcription_candidate(
            candidate,
            args=SimpleNamespace(apply=True, ffprobe="ffprobe"),
        )

    assert json.loads(metadata_path.read_text()) == changed


def test_model_label_must_be_filename_component():
    with pytest.raises(ValueError, match="filename component"):
        transcript_batch.transcript_relative_path("2026-05-24-0630", "../escape")


def test_dry_run_writes_nothing(tmp_path):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()
    media_path = vlog_dir / "2026-05-24-0630.mkv"
    media_path.write_bytes(b"media")
    metadata_path = vlog_dir / "2026-05-24-0630.json"
    original = write_metadata(metadata_path)

    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]
    result = transcript_batch.process_transcription_candidate(
        candidate,
        args=SimpleNamespace(apply=False),
    )

    assert result == "dry_run: 2026-05-24-0630: would transcribe"
    assert json.loads(metadata_path.read_text()) == original
    assert not (vlog_dir / "transcripts").exists()


def test_apply_transcribes_then_updates_metadata(monkeypatch, tmp_path):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()
    media_path = vlog_dir / "2026-05-24-0630.mkv"
    media_path.write_bytes(b"media")
    metadata_path = vlog_dir / "2026-05-24-0630.json"
    write_metadata(metadata_path)

    def fake_extract(_media_path, wav_path, *, ffmpeg):
        wav_path.write_bytes(b"wav")

    def fake_whisper(_wav_path, output_base, *, whisper_cli, model, threads):
        transcript_path = Path(f"{output_base}.json")
        transcript_path.write_text(json.dumps(valid_transcript()) + "\n")
        return transcript_path

    monkeypatch.setattr(transcript_batch, "extract_wav", fake_extract)
    monkeypatch.setattr(transcript_batch, "run_whisper", fake_whisper)
    monkeypatch.setattr(
        transcript_batch, "media_duration_ms", lambda *_args, **_kw: 2500
    )

    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]
    result = transcript_batch.process_transcription_candidate(
        candidate,
        args=SimpleNamespace(
            apply=True,
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
            whisper_cli="whisper-cli",
            model=Path("model.bin"),
            model_label=MODEL_LABEL,
            threads=10,
            tmp_dir=None,
        ),
    )

    assert result == (
        f"transcribed: 2026-05-24-0630: transcripts/2026-05-24-0630.{MODEL_LABEL}.json"
    )
    assert candidate.transcript_path.exists()
    updated = json.loads(metadata_path.read_text())
    assert updated["metadata_quality"] == "full"
    assert (
        updated["transcript_file"] == f"transcripts/2026-05-24-0630.{MODEL_LABEL}.json"
    )


def test_whisper_failure_leaves_metadata_unchanged(monkeypatch, tmp_path):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()
    media_path = vlog_dir / "2026-05-24-0630.mkv"
    media_path.write_bytes(b"media")
    metadata_path = vlog_dir / "2026-05-24-0630.json"
    original = write_metadata(metadata_path)

    def fake_whisper(_wav_path, _output_base, *, whisper_cli, model, threads):
        raise subprocess.CalledProcessError(1, "whisper-cli")

    monkeypatch.setattr(transcript_batch, "extract_wav", lambda *_args, **_kw: None)
    monkeypatch.setattr(transcript_batch, "run_whisper", fake_whisper)

    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]
    with pytest.raises(subprocess.CalledProcessError):
        transcript_batch.process_transcription_candidate(
            candidate,
            args=SimpleNamespace(
                apply=True,
                ffmpeg="ffmpeg",
                ffprobe="ffprobe",
                whisper_cli="whisper-cli",
                model=Path("model.bin"),
                model_label=MODEL_LABEL,
                threads=10,
                tmp_dir=None,
            ),
        )

    assert json.loads(metadata_path.read_text()) == original
    assert not candidate.transcript_path.exists()


def test_invalid_existing_tags_do_not_block_transcript_link(monkeypatch, tmp_path):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()
    media_path = vlog_dir / "2026-05-24-0630.mkv"
    media_path.write_bytes(b"media")
    metadata_path = vlog_dir / "2026-05-24-0630.json"
    original = write_metadata(metadata_path, {"tags": ["not-in-vocabulary"]})

    def fake_extract(_media_path, wav_path, *, ffmpeg):
        wav_path.write_bytes(b"wav")

    def fake_whisper(_wav_path, output_base, *, whisper_cli, model, threads):
        transcript_path = Path(f"{output_base}.json")
        transcript_path.write_text(json.dumps(valid_transcript()) + "\n")
        return transcript_path

    monkeypatch.setattr(transcript_batch, "extract_wav", fake_extract)
    monkeypatch.setattr(transcript_batch, "run_whisper", fake_whisper)
    monkeypatch.setattr(
        transcript_batch, "media_duration_ms", lambda *_args, **_kw: 2500
    )

    candidate = transcript_batch.discover_transcription_candidates(
        vlog_dir, model_label=MODEL_LABEL
    )[0]
    result = transcript_batch.process_transcription_candidate(
        candidate,
        args=SimpleNamespace(
            apply=True,
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
            whisper_cli="whisper-cli",
            model=Path("model.bin"),
            model_label=MODEL_LABEL,
            threads=10,
            tmp_dir=None,
        ),
    )

    assert result == (
        f"transcribed: 2026-05-24-0630: transcripts/2026-05-24-0630.{MODEL_LABEL}.json"
    )
    updated = json.loads(metadata_path.read_text())
    assert updated["tags"] == original["tags"]
    assert updated["metadata_quality"] == "full"
    assert (
        updated["transcript_file"] == f"transcripts/2026-05-24-0630.{MODEL_LABEL}.json"
    )
    assert candidate.transcript_path.exists()


def test_discover_translation_candidates_requires_source_and_media(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / f"2026-05-24-0630.{MODEL_LABEL}.json"
    write_source(source)
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")

    candidate = transcript_batch.discover_translation_candidates(
        vlog_dir,
        source_label=MODEL_LABEL,
        target_label=TARGET_LABEL,
    )[0]

    assert candidate.action == "translate"
    assert candidate.media_path.name == "2026-05-24-0630.mkv"


def test_translation_dry_run_writes_nothing(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / f"2026-05-24-0630.{MODEL_LABEL}.json"
    write_source(source)
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")
    candidate = transcript_batch.discover_translation_candidates(
        vlog_dir,
        source_label=MODEL_LABEL,
        target_label=TARGET_LABEL,
    )[0]

    result = transcript_batch.process_translation_candidate(
        candidate, args=SimpleNamespace(apply=False)
    )

    assert result == "dry_run: 2026-05-24-0630: would translate"
    assert not candidate.target_path.exists()


def test_apply_whisper_translation_preserves_provenance(monkeypatch, tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / f"2026-05-24-0630.{MODEL_LABEL}.json"
    write_source(source)
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")

    def fake_extract(_media_path, wav_path, *, ffmpeg):
        wav_path.write_bytes(b"wav")

    def fake_whisper(
        _wav_path,
        output_base,
        *,
        whisper_cli,
        model,
        threads,
        translate=False,
    ):
        assert translate is True
        path = Path(f"{output_base}.json")
        payload = valid_transcript()
        payload["transcription"][0]["text"] = " translated hello"
        payload["transcription"][1]["text"] = " translated world"
        path.write_text(json.dumps(payload) + "\n")
        return path

    monkeypatch.setattr(transcript_batch, "extract_wav", fake_extract)
    monkeypatch.setattr(transcript_batch, "run_whisper", fake_whisper)
    monkeypatch.setattr(
        transcript_batch, "media_duration_ms", lambda *_args, **_kwargs: 2_500
    )
    candidate = transcript_batch.discover_translation_candidates(
        vlog_dir,
        source_label=MODEL_LABEL,
        target_label=TARGET_LABEL,
    )[0]

    result = transcript_batch.process_translation_candidate(
        candidate,
        args=SimpleNamespace(
            apply=True,
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
            whisper_cli="whisper-cli",
            model=Path("model.bin"),
            target_label=TARGET_LABEL,
            threads=10,
            tmp_dir=None,
        ),
    )

    payload = json.loads(candidate.target_path.read_text())
    assert result.startswith("translated: 2026-05-24-0630")
    assert payload["translation"]["source_file"] == source.name
    assert payload["translation"]["source_sha256"] == transcript_batch.source_sha256(
        source
    )
    assert payload["transcription"][0]["source_text"] == "hello"
    assert payload["transcription"][0]["text"] == " translated hello"


def test_invalid_translation_source_is_reported(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / f"2026-05-24-0630.{MODEL_LABEL}.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"transcription":[]}\n')
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")

    candidate = transcript_batch.discover_translation_candidates(
        vlog_dir,
        source_label=MODEL_LABEL,
        target_label=TARGET_LABEL,
    )[0]

    assert candidate.action == "invalid_source"


def test_existing_translation_provenance_controls_skip(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / f"2026-05-24-0630.{MODEL_LABEL}.json"
    write_source(source)
    (vlog_dir / "2026-05-24-0630.mkv").write_bytes(b"media")
    target = source.with_name(f"2026-05-24-0630.{TARGET_LABEL}.json")
    target.write_text(json.dumps(valid_translation(source)) + "\n")

    candidate = transcript_batch.discover_translation_candidates(
        vlog_dir,
        source_label=MODEL_LABEL,
        target_label=TARGET_LABEL,
    )[0]
    assert candidate.action == "skip_existing"

    payload = json.loads(target.read_text())
    payload["translation"]["source_sha256"] = "0" * 64
    target.write_text(json.dumps(payload) + "\n")
    candidate = transcript_batch.discover_translation_candidates(
        vlog_dir,
        source_label=MODEL_LABEL,
        target_label=TARGET_LABEL,
    )[0]
    assert candidate.action == "stale_existing"


def test_translation_requires_exactly_one_media_file(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / f"2026-05-24-0630.{MODEL_LABEL}.json"
    write_source(source)

    candidate = transcript_batch.discover_translation_candidates(
        vlog_dir,
        source_label=MODEL_LABEL,
        target_label=TARGET_LABEL,
    )[0]

    assert candidate.action == "invalid_media"


def test_translation_labels_must_be_filename_components(tmp_path):
    with pytest.raises(ValueError, match="filename component"):
        transcript_batch.discover_translation_candidates(
            tmp_path,
            source_label="../source",
            target_label=TARGET_LABEL,
        )


def test_cli_requires_explicit_mode():
    with pytest.raises(SystemExit):
        transcript_batch.parse_args([])

    assert transcript_batch.parse_args(["transcribe"]).mode == "transcribe"
    assert transcript_batch.parse_args(["translate"]).mode == "translate"
