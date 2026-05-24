import json
from datetime import datetime, timezone

import pytest

import scripts.privledger as privledger


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 5, 24, 6, 30, tzinfo=timezone.utc).astimezone(tz)


def run_supervisor(monkeypatch, tmp_path, *, artifact, recorder_exit, writer=None):
    vlog_dir = tmp_path / "vlog"
    scripts_dir = tmp_path / "scripts"
    vlog_dir.mkdir()
    scripts_dir.mkdir()
    record_script = scripts_dir / "record.sh"
    record_script.write_text("#!/usr/bin/env bash\nexit 0\n")

    class FakePopen:
        pid = 12345

        def __init__(self, _cmd, env, start_new_session):
            assert start_new_session is True
            ts = env["TIMESTAMP"]
            if artifact in {"good", "both"}:
                (vlog_dir / f"{ts}.mkv").write_bytes(b"good media")
            if artifact in {"bad", "both"}:
                (vlog_dir / f"{ts}.mkv.bad.mkv").write_bytes(b"bad media")

        def wait(self):
            return recorder_exit

        def poll(self):
            return recorder_exit

    monkeypatch.setattr(privledger, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(privledger, "RECORD_SCRIPT", record_script)
    monkeypatch.setattr(privledger, "SCHEMA_VERSION", "1")
    monkeypatch.setattr(privledger, "PIPELINE_VERSION", "0.1.0")
    monkeypatch.setattr(privledger, "CUSTOM_ENABLED", False)
    monkeypatch.setattr(privledger, "datetime", FixedDateTime)
    monkeypatch.setattr(
        privledger,
        "ENV",
        {
            "VIDEO_DEV": "/dev/video-mock",
            "AUDIO_SRC": "mock-source",
            "VAAPI_DEV": "/dev/dri/mock",
            "SCHEMA_VERSION": "1",
            "PIPELINE_VERSION": "0.1.0",
        },
    )
    monkeypatch.setattr(privledger, "detect_video_device_name", lambda _dev: "mock camera")
    monkeypatch.setattr(privledger.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(privledger.subprocess, "Popen", FakePopen)
    if writer is not None:
        monkeypatch.setattr(privledger, "write_metadata_atomic", writer)

    with pytest.raises(SystemExit) as exc:
        privledger.main()

    return exc.value.code, vlog_dir


def read_metadata(vlog_dir):
    return json.loads((vlog_dir / "2026-05-24-0630.json").read_text())


class TestSupervisorRecordingMatrix:
    def test_successful_capture_writes_basic_metadata(self, monkeypatch, tmp_path):
        code, vlog_dir = run_supervisor(
            monkeypatch, tmp_path, artifact="good", recorder_exit=0
        )

        data = read_metadata(vlog_dir)

        assert code == 0
        assert data["media_file"] == "2026-05-24-0630.mkv"
        assert data["metadata_quality"] == "basic"

    def test_degraded_capture_writes_bad_metadata_and_exits_nonzero(
        self, monkeypatch, tmp_path
    ):
        code, vlog_dir = run_supervisor(
            monkeypatch, tmp_path, artifact="bad", recorder_exit=1
        )

        data = read_metadata(vlog_dir)

        assert code == 1
        assert data["media_file"] == "2026-05-24-0630.mkv.bad.mkv"
        assert data["metadata_quality"] == "bad"

    def test_no_artifact_with_nonzero_exit_writes_no_metadata(self, monkeypatch, tmp_path):
        code, vlog_dir = run_supervisor(
            monkeypatch, tmp_path, artifact="none", recorder_exit=1
        )

        assert code == 1
        assert not (vlog_dir / "2026-05-24-0630.json").exists()

    def test_no_artifact_with_zero_exit_still_fails(self, monkeypatch, tmp_path):
        code, vlog_dir = run_supervisor(
            monkeypatch, tmp_path, artifact="none", recorder_exit=0
        )

        assert code == 1
        assert not (vlog_dir / "2026-05-24-0630.json").exists()

    def test_both_artifacts_violate_invariant_and_write_no_metadata(
        self, monkeypatch, tmp_path
    ):
        code, vlog_dir = run_supervisor(
            monkeypatch, tmp_path, artifact="both", recorder_exit=0
        )

        assert code == 2
        assert not (vlog_dir / "2026-05-24-0630.json").exists()

    def test_bad_artifact_is_failure_even_if_recorder_exit_is_zero(
        self, monkeypatch, tmp_path
    ):
        code, vlog_dir = run_supervisor(
            monkeypatch, tmp_path, artifact="bad", recorder_exit=0
        )

        data = read_metadata(vlog_dir)

        assert data["metadata_quality"] == "bad"
        assert code != 0

    def test_metadata_write_failure_preserves_media_and_writes_no_json(
        self, monkeypatch, tmp_path
    ):
        def failing_writer(**_kwargs):
            raise ValueError("mock metadata failure")

        code, vlog_dir = run_supervisor(
            monkeypatch,
            tmp_path,
            artifact="good",
            recorder_exit=0,
            writer=failing_writer,
        )

        assert code == 1
        assert (vlog_dir / "2026-05-24-0630.mkv").exists()
        assert not (vlog_dir / "2026-05-24-0630.json").exists()
