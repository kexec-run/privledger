import json
import subprocess
from types import SimpleNamespace

import scripts.translate_batch as translate_batch
from tests.test_transcribe_batch import valid_transcript


def write_source(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(valid_transcript()) + "\n")


def test_discover_candidates_finds_source_transcripts(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / "2026-05-24-0630.whisper-large-v3-source.json"
    write_source(source)

    candidates = translate_batch.discover_candidates(
        vlog_dir,
        source_label="whisper-large-v3-source",
        target_label="whisper-large-v3-translate-en",
    )

    assert len(candidates) == 1
    assert candidates[0].action == "translate"
    assert (
        candidates[0].target_path.name
        == "2026-05-24-0630.whisper-large-v3-translate-en.json"
    )


def test_dry_run_writes_nothing(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / "2026-05-24-0630.whisper-large-v3-source.json"
    write_source(source)

    candidate = translate_batch.discover_candidates(
        vlog_dir,
        source_label="whisper-large-v3-source",
        target_label="whisper-large-v3-translate-en",
    )[0]
    result = translate_batch.process_candidate(
        candidate,
        args=SimpleNamespace(apply=False),
    )

    assert result == (
        "dry_run: 2026-05-24-0630.whisper-large-v3-source.json: would translate"
    )
    assert not candidate.target_path.exists()


def test_apply_requires_translator_command(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / "2026-05-24-0630.whisper-large-v3-source.json"
    write_source(source)

    candidate = translate_batch.discover_candidates(
        vlog_dir,
        source_label="whisper-large-v3-source",
        target_label="whisper-large-v3-translate-en",
    )[0]
    result = translate_batch.process_candidate(
        candidate,
        args=SimpleNamespace(apply=True, translator_cmd=None),
    )

    assert result.startswith("missing_translator:")
    assert not candidate.target_path.exists()


def test_run_translator_command_contract(monkeypatch):
    calls = []

    def fake_run(command, *, input, capture_output, text, check):
        calls.append((command, json.loads(input), capture_output, text, check))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"texts": ["नमस्ते translated"]}),
            stderr="",
        )

    monkeypatch.setattr(translate_batch.subprocess, "run", fake_run)

    translated = translate_batch.run_translator_command(
        "translator --json",
        ["नमस्ते"],
        target_language="en",
    )

    assert translated == ["नमस्ते translated"]
    assert calls[0][0] == ["translator", "--json"]
    assert calls[0][1] == {"target_language": "en", "texts": ["नमस्ते"]}
    assert calls[0][2:] == (True, True, True)


def test_translate_candidate_preserves_timestamps_and_source_text(
    monkeypatch, tmp_path
):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / "2026-05-24-0630.whisper-large-v3-source.json"
    write_source(source)

    def fake_translate(command, texts, *, target_language):
        assert target_language == "en"
        return [f"translated:{text.strip()}" for text in texts]

    monkeypatch.setattr(translate_batch, "run_translator_command", fake_translate)

    candidate = translate_batch.discover_candidates(
        vlog_dir,
        source_label="whisper-large-v3-source",
        target_label="whisper-large-v3-translate-en",
    )[0]
    result = translate_batch.process_candidate(
        candidate,
        args=SimpleNamespace(
            apply=True,
            translator_cmd="translator --json",
            target_language="en",
            batch_size=16,
        ),
    )

    assert result == (
        "translated: 2026-05-24-0630.whisper-large-v3-source.json: "
        "2026-05-24-0630.whisper-large-v3-translate-en.json"
    )
    payload = json.loads(candidate.target_path.read_text())
    source_payload = json.loads(source.read_text())
    assert payload["result"] == {"language": "en", "source_language": "en"}
    assert payload["translation"]["source_file"] == source.name
    assert (
        payload["transcription"][0]["timestamps"]
        == source_payload["transcription"][0]["timestamps"]
    )
    assert (
        payload["transcription"][0]["offsets"]
        == source_payload["transcription"][0]["offsets"]
    )
    assert payload["transcription"][0]["source_text"] == " hello"
    assert payload["transcription"][0]["text"] == "translated:hello"


def test_invalid_source_is_reported(tmp_path):
    vlog_dir = tmp_path / "vlog"
    source = vlog_dir / "transcripts" / "2026-05-24-0630.whisper-large-v3-source.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps({"transcription": []}) + "\n")

    candidate = translate_batch.discover_candidates(
        vlog_dir,
        source_label="whisper-large-v3-source",
        target_label="whisper-large-v3-translate-en",
    )[0]

    assert candidate.action == "invalid_source"
    assert "non-empty list" in candidate.reason
