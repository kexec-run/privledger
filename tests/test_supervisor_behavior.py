import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import privledger  # noqa: E402


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 5, 24, 6, 30, tzinfo=timezone.utc).astimezone(tz)


def run_supervisor(
    monkeypatch,
    tmp_path,
    *,
    artifact,
    recorder_exit,
    writer=None,
    config=None,
):
    vlog_dir = tmp_path / "vlog"
    scripts_dir = tmp_path / "scripts"
    vlog_dir.mkdir()
    scripts_dir.mkdir()
    if config is None:
        record_script = scripts_dir / "record-linux.sh"
        config = privledger.RecorderConfig(
            name="test-linux",
            record_script=record_script,
            good_suffix=".mkv",
            bad_suffix=".mkv.bad.mkv",
            required_env_vars=(
                "VIDEO_DEV",
                "AUDIO_SRC",
                "VAAPI_DEV",
                "SCHEMA_VERSION",
                "PIPELINE_VERSION",
            ),
            video_device_env="VIDEO_DEV",
        )
    config.record_script.write_text("#!/usr/bin/env bash\nexit 0\n")

    class FakePopen:
        pid = 12345

        def __init__(self, _cmd, env, start_new_session):
            assert start_new_session is True
            ts = env["TIMESTAMP"]
            if artifact in {"good", "both"}:
                (vlog_dir / f"{ts}{config.good_suffix}").write_bytes(b"good media")
            if artifact in {"bad", "both"}:
                (vlog_dir / f"{ts}{config.bad_suffix}").write_bytes(b"bad media")

        def wait(self):
            return recorder_exit

        def poll(self):
            return recorder_exit

    monkeypatch.setattr(privledger, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(privledger, "CONFIG_ENV", tmp_path / "config" / "env")
    monkeypatch.setattr(
        privledger,
        "load_config_env",
        lambda _config: (
            {
                "VIDEO_DEV": "/dev/video-mock",
                "AUDIO_SRC": "mock-source",
                "VAAPI_DEV": "/dev/dri/mock",
                "SCHEMA_VERSION": "1",
                "PIPELINE_VERSION": "0.1.0",
                "AVCAM_CAMERA": "Brio",
            },
            "1",
            "0.1.0",
        ),
    )
    monkeypatch.setattr(privledger, "load_schema", lambda _config: {})
    monkeypatch.setattr(privledger, "load_custom_schema", lambda: (False, None))
    monkeypatch.setattr(privledger, "datetime", FixedDateTime)
    monkeypatch.setattr(
        privledger,
        "detect_video_device_name",
        lambda _config, _env: "mock camera",
    )
    monkeypatch.setattr(privledger.signal, "signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(privledger.subprocess, "Popen", FakePopen)
    if writer is not None:
        monkeypatch.setattr(privledger, "write_metadata_atomic", writer)

    with pytest.raises(SystemExit) as exc:
        privledger.supervise_capture(config)

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

    def test_no_artifact_with_nonzero_exit_writes_no_metadata(
        self, monkeypatch, tmp_path
    ):
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

    def test_macos_capture_uses_mov_artifact_names(self, monkeypatch, tmp_path):
        record_script = tmp_path / "scripts" / "record-mac.sh"
        config = privledger.RecorderConfig(
            name="test-mac",
            record_script=record_script,
            good_suffix=".mov",
            bad_suffix=".mov.bad.mov",
            required_env_vars=("SCHEMA_VERSION", "PIPELINE_VERSION"),
            video_device_env="AVCAM_CAMERA",
            default_video_device="Brio",
        )

        code, vlog_dir = run_supervisor(
            monkeypatch,
            tmp_path,
            artifact="good",
            recorder_exit=0,
            config=config,
        )

        data = read_metadata(vlog_dir)

        assert code == 0
        assert data["media_file"] == "2026-05-24-0630.mov"
        assert data["metadata_quality"] == "basic"


class TestPlatformSelection:
    def test_main_selects_macos_config_on_darwin(self, monkeypatch):
        selected = []

        monkeypatch.setattr(privledger.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(
            privledger, "supervise_capture", lambda config: selected.append(config)
        )

        privledger.main()

        assert selected[0].name == "privledger-mac"
        assert selected[0].good_suffix == ".mov"

    def test_main_selects_linux_config_when_not_darwin(self, monkeypatch):
        selected = []

        monkeypatch.setattr(privledger.platform, "system", lambda: "Linux")
        monkeypatch.setattr(
            privledger, "supervise_capture", lambda config: selected.append(config)
        )

        privledger.main()

        assert selected[0].name == "privledger-linux"
        assert selected[0].good_suffix == ".mkv"


class TestCustomSchemaLoading:
    def test_invalid_custom_schema_fails_cleanly_before_recording(
        self, monkeypatch, capsys
    ):
        monkeypatch.setenv("CUSTOM_ENABLED", "true")

        def fail_load(_path):
            raise ValueError("bad yaml")

        import metadata.custom_schema as custom_schema

        monkeypatch.setattr(custom_schema, "load_custom_schema", fail_load)

        with pytest.raises(SystemExit) as exc:
            privledger.load_custom_schema()

        captured = capsys.readouterr()

        assert exc.value.code == 1
        assert "[privledger] ERROR: invalid custom schema: bad yaml" in captured.err
