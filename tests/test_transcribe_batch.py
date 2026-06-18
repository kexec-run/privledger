import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.transcribe_batch as transcribe_batch
from tests.test_enrich_behavior import base_metadata
from tests.test_writer_invariants import MOCK_SCHEMA


MODEL_LABEL = "whisper-large-v3-source"


def write_metadata(path: Path, data=None):
    payload = base_metadata()
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


def test_validate_transcript_accepts_observed_shape():
    transcribe_batch.validate_transcript_payload(
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
    with pytest.raises(transcribe_batch.TranscriptValidationError, match=match):
        transcribe_batch.validate_transcript_payload(payload)


def test_run_whisper_uses_source_transcription_mode(monkeypatch, tmp_path):
    calls = []

    def fake_run(command, *, check):
        calls.append(command)
        assert check is True

    monkeypatch.setattr(transcribe_batch.subprocess, "run", fake_run)

    result = transcribe_batch.run_whisper(
        tmp_path / "audio.wav",
        tmp_path / "out",
        whisper_cli="whisper-cli",
        model=Path("model.bin"),
        threads=10,
    )

    assert result == tmp_path / "out.json"
    assert "-tr" not in calls[0]
    assert "-oj" in calls[0]


def test_discover_candidates_reports_batch_actions(tmp_path):
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
        for candidate in transcribe_batch.discover_candidates(
            vlog_dir, model_label=MODEL_LABEL
        )
    }

    assert actions == {
        "2026-05-24-0630": "transcribe",
        "2026-05-24-0700": "missing_metadata",
        "2026-05-24-0800": "skip_linked",
    }


def test_dry_run_writes_nothing(tmp_path):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()
    media_path = vlog_dir / "2026-05-24-0630.mkv"
    media_path.write_bytes(b"media")
    metadata_path = vlog_dir / "2026-05-24-0630.json"
    original = write_metadata(metadata_path)

    candidate = transcribe_batch.discover_candidates(vlog_dir, model_label=MODEL_LABEL)[
        0
    ]
    result = transcribe_batch.process_candidate(
        candidate,
        args=SimpleNamespace(apply=False),
        schema=MOCK_SCHEMA,
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

    monkeypatch.setattr(transcribe_batch, "extract_wav", fake_extract)
    monkeypatch.setattr(transcribe_batch, "run_whisper", fake_whisper)
    monkeypatch.setattr(
        transcribe_batch, "media_duration_ms", lambda *_args, **_kw: 2500
    )

    candidate = transcribe_batch.discover_candidates(vlog_dir, model_label=MODEL_LABEL)[
        0
    ]
    result = transcribe_batch.process_candidate(
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
        schema=MOCK_SCHEMA,
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

    monkeypatch.setattr(transcribe_batch, "extract_wav", lambda *_args, **_kw: None)
    monkeypatch.setattr(transcribe_batch, "run_whisper", fake_whisper)

    candidate = transcribe_batch.discover_candidates(vlog_dir, model_label=MODEL_LABEL)[
        0
    ]
    with pytest.raises(subprocess.CalledProcessError):
        transcribe_batch.process_candidate(
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
            schema=MOCK_SCHEMA,
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

    monkeypatch.setattr(transcribe_batch, "extract_wav", fake_extract)
    monkeypatch.setattr(transcribe_batch, "run_whisper", fake_whisper)
    monkeypatch.setattr(
        transcribe_batch, "media_duration_ms", lambda *_args, **_kw: 2500
    )

    candidate = transcribe_batch.discover_candidates(vlog_dir, model_label=MODEL_LABEL)[
        0
    ]
    result = transcribe_batch.process_candidate(
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
        schema=MOCK_SCHEMA,
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
