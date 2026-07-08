import json
from datetime import datetime, timezone

import pytest

import scripts.enrich as enrich
import scripts.privledger as privledger


class FixedDateTime:
    @staticmethod
    def now(tz=None):
        return datetime(2026, 5, 24, 6, 30, tzinfo=timezone.utc).astimezone(tz)


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


def write_metadata(path, data=None):
    payload = base_metadata()
    if data:
        payload.update(data)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return payload


def run_enrich(monkeypatch, tmp_path, metadata, input_lines):
    vlog_dir = tmp_path / "vlog"
    vlog_dir.mkdir()
    meta_path = vlog_dir / "2026-05-24-0630.json"
    original = write_metadata(meta_path, metadata)
    inputs = iter(input_lines)

    monkeypatch.setattr(enrich, "VLOG_DIR", vlog_dir)
    monkeypatch.setattr(enrich, "CUSTOM_ENABLED", False)
    monkeypatch.setattr(enrich, "SCHEMA_VERSION", "1")
    monkeypatch.setattr(enrich, "PIPELINE_VERSION", "0.1.0")
    monkeypatch.setattr(enrich.sys, "argv", ["enrich.py", "2026-05-24-0630"])
    monkeypatch.setattr(enrich, "_readline", lambda _prompt: next(inputs))
    monkeypatch.setattr(enrich, "resolve_custom", lambda *_args: enrich._MISSING)

    try:
        enrich.main()
        code = None
    except SystemExit as exc:
        code = exc.code

    return code, original, json.loads(meta_path.read_text())


class TestEnrichmentContract:
    def test_empty_input_keeps_existing_values(self, monkeypatch, tmp_path):
        original_values = {
            "mood": 3,
            "energy": 4,
            "sleep_hours": 7.5,
            "tags": ["programming"],
            "focus_domain": "systems",
            "location": "office",
        }

        code, original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            original_values,
            input_lines=["", "", "", "", "", "", "", "", "", ""],
        )

        assert code is None
        assert updated == original

    def test_invalid_numeric_input_retries_before_write(self, monkeypatch, tmp_path):
        code, _original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {},
            input_lines=["bad", "6", "4", "", "", "", "", "", "", "", "", ""],
        )

        assert code is None
        assert updated["mood"] == 4

    def test_tag_selection_normalizes_dedupes_and_updates_metadata(
        self, monkeypatch, tmp_path
    ):
        code, _original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {"tags": ["programming"]},
            input_lines=["", "", "", "", "", "", "", "", "Fatigue, programming", ""],
        )

        assert code is None
        assert updated["tags"] == ["fatigue", "programming"]

    def test_tag_overflow_reprompts_and_leaves_tags_unchanged(
        self, monkeypatch, tmp_path
    ):
        code, original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {"tags": ["programming", "fatigue", "sleep", "exercise", "planning"]},
            input_lines=["", "", "", "", "", "", "", "", "systems", "", ""],
        )

        assert code is None
        assert updated == original

    def test_enrichment_preserves_immutable_fields(self, monkeypatch, tmp_path):
        code, original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {"tags": ["fatigue"]},
            input_lines=["", "", "", "", "", "", "", "sleep", "", "home"],
        )

        assert code is None
        assert updated["id"] == original["id"]
        assert updated["timestamp_utc"] == original["timestamp_utc"]
        assert updated["media_file"] == original["media_file"]
        assert updated["focus_domain"] == "sleep"
        assert updated["tags"] == ["fatigue"]
        assert updated["location"] == "home"

    def test_recording_pipeline_metadata_can_be_enriched(self, monkeypatch, tmp_path):
        vlog_dir = tmp_path / "vlog"
        scripts_dir = tmp_path / "scripts"
        vlog_dir.mkdir()
        scripts_dir.mkdir()
        record_script = scripts_dir / "record-linux.sh"
        record_script.write_text("#!/usr/bin/env bash\nexit 0\n")
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

        class FakePopen:
            pid = 12345

            def __init__(self, _cmd, env, start_new_session):
                assert start_new_session is True
                (vlog_dir / f"{env['TIMESTAMP']}.mkv").write_bytes(b"good media")

            def wait(self):
                return 0

            def poll(self):
                return 0

        monkeypatch.setattr(privledger, "ROOT_DIR", tmp_path)
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

        with pytest.raises(SystemExit) as capture_exit:
            privledger.supervise_capture(config)

        assert capture_exit.value.code == 0
        meta_path = vlog_dir / "2026-05-24-0630.json"
        captured = json.loads(meta_path.read_text())

        inputs = iter(
            ["4", "3", "2", "1", "7.5", "120", "72", "sleep", "fatigue", "home"]
        )
        monkeypatch.setattr(enrich, "VLOG_DIR", vlog_dir)
        monkeypatch.setattr(enrich, "CUSTOM_ENABLED", False)
        monkeypatch.setattr(enrich, "SCHEMA_VERSION", "1")
        monkeypatch.setattr(enrich, "PIPELINE_VERSION", "0.1.0")
        monkeypatch.setattr(enrich.sys, "argv", ["enrich.py", "2026-05-24-0630"])
        monkeypatch.setattr(enrich, "_readline", lambda _prompt: next(inputs))
        monkeypatch.setattr(enrich, "resolve_custom", lambda *_args: enrich._MISSING)

        enrich.main()

        updated = json.loads(meta_path.read_text())
        for field in (
            "id",
            "timestamp_utc",
            "timestamp_local",
            "schema_version",
            "pipeline_version",
            "metadata_quality",
            "media_file",
            "video_device",
            "transcript_file",
        ):
            assert updated[field] == captured[field]
        assert updated["mood"] == 4
        assert updated["energy"] == 3
        assert updated["stress"] == 2
        assert updated["sleepiness"] == 1
        assert updated["sleep_hours"] == 7.5
        assert updated["caffeine_mg"] == 120
        assert updated["body_weight"] == 72
        assert updated["focus_domain"] == "sleep"
        assert updated["tags"] == ["fatigue"]
        assert updated["location"] == "home"

    def test_invalid_focus_domain_reprompts_before_write(self, monkeypatch, tmp_path):
        code, _original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {"tags": ["programming"], "focus_domain": None},
            input_lines=["", "", "", "", "", "", "", "notatag", "fatigue", "", ""],
        )

        assert code is None
        assert updated["focus_domain"] == "fatigue"
        assert updated["tags"] == ["programming"]

    def test_existing_focus_duplicate_reprompts_before_write(
        self, monkeypatch, tmp_path
    ):
        code, _original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {"tags": ["chores", "sleep"], "focus_domain": "family"},
            input_lines=["", "", "", "", "", "", "", "sleep", "finance", "", ""],
        )

        assert code is None
        assert updated["focus_domain"] == "finance"
        assert updated["tags"] == ["chores", "sleep"]

    def test_blank_duplicated_current_focus_reprompts_before_write(
        self, monkeypatch, tmp_path
    ):
        code, _original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {"tags": ["chores", "sleep"], "focus_domain": "sleep"},
            input_lines=["", "", "", "", "", "", "", "", "finance", "", ""],
        )

        assert code is None
        assert updated["focus_domain"] == "finance"
        assert updated["tags"] == ["chores", "sleep"]

    def test_cancelled_enrichment_writes_nothing(self, monkeypatch, tmp_path):
        vlog_dir = tmp_path / "vlog"
        vlog_dir.mkdir()
        meta_path = vlog_dir / "2026-05-24-0630.json"
        original = write_metadata(meta_path, {"tags": ["programming"]})

        monkeypatch.setattr(enrich, "VLOG_DIR", vlog_dir)
        monkeypatch.setattr(enrich.sys, "argv", ["enrich.py", "2026-05-24-0630"])
        monkeypatch.setattr(
            enrich,
            "_readline",
            lambda _prompt: (_ for _ in ()).throw(KeyboardInterrupt),
        )

        with pytest.raises(SystemExit) as exc:
            enrich.main()

        assert exc.value.code == 0
        assert json.loads(meta_path.read_text()) == original

    def test_direct_json_enrichment_updates_metadata(
        self, monkeypatch, tmp_path, capsys
    ):
        vlog_dir = tmp_path / "vlog"
        vlog_dir.mkdir()
        meta_path = vlog_dir / "2026-05-24-0630.json"
        write_metadata(meta_path, {"tags": ["programming"]})

        monkeypatch.setattr(enrich, "VLOG_DIR", vlog_dir)
        monkeypatch.setattr(enrich, "CUSTOM_ENABLED", False)
        monkeypatch.setattr(
            enrich.sys, "argv", ["enrich.py", "--json", "2026-05-24-0630"]
        )
        monkeypatch.setattr(
            enrich.sys,
            "stdin",
            type(
                "Input",
                (),
                {
                    "read": lambda _self: "",
                },
            )(),
        )
        monkeypatch.setattr(
            enrich.json,
            "load",
            lambda _stdin: {"mood": 5, "tags": ["sleep"], "location": "desk"},
        )

        enrich.main()

        updated = json.loads(meta_path.read_text())
        result = json.loads(capsys.readouterr().out)
        assert result["ok"] is True
        assert result["id"] == "2026-05-24-0630"
        assert result["metadata"] == updated
        assert result["changed"] == ["location", "mood", "tags"]
        assert updated["mood"] == 5
        assert updated["tags"] == ["sleep"]
        assert updated["location"] == "desk"

    def test_direct_json_validation_error_is_structured(
        self, monkeypatch, tmp_path, capsys
    ):
        vlog_dir = tmp_path / "vlog"
        vlog_dir.mkdir()
        meta_path = vlog_dir / "2026-05-24-0630.json"
        original = write_metadata(meta_path, {"tags": ["programming"]})

        monkeypatch.setattr(enrich, "VLOG_DIR", vlog_dir)
        monkeypatch.setattr(enrich, "CUSTOM_ENABLED", False)
        monkeypatch.setattr(
            enrich.sys, "argv", ["enrich.py", "--json", "2026-05-24-0630"]
        )
        monkeypatch.setattr(
            enrich.json,
            "load",
            lambda _stdin: {"mood": 99},
        )

        with pytest.raises(SystemExit) as exc:
            enrich.main()

        assert exc.value.code == 1
        assert json.loads(meta_path.read_text()) == original
        error = json.loads(capsys.readouterr().out)
        assert error["ok"] is False
        assert error["id"] == "2026-05-24-0630"
        assert error["metadata"] == original
        assert error["changed"] == []
        assert "mood" in error["field_errors"]
        assert "greater than the maximum" in error["field_errors"]["mood"]

    def test_describe_enrichment_returns_tag_and_custom_shape(
        self, monkeypatch, tmp_path, capsys
    ):
        vlog_dir = tmp_path / "vlog"
        vlog_dir.mkdir()
        meta_path = vlog_dir / "2026-05-24-0630.json"
        write_metadata(meta_path, {"tags": ["programming"]})

        monkeypatch.setattr(enrich, "VLOG_DIR", vlog_dir)
        monkeypatch.setattr(enrich, "CUSTOM_ENABLED", False)
        monkeypatch.setattr(enrich, "load_tag_vocabulary", lambda: ["programming"])
        monkeypatch.setattr(
            enrich.sys, "argv", ["enrich.py", "--describe", "2026-05-24-0630"]
        )

        enrich.main()
        described = json.loads(capsys.readouterr().out)
        assert described["id"] == "2026-05-24-0630"
        assert described["values"]["tags"] == ["programming"]
        assert described["tag_vocabulary"] == ["programming"]
        assert described["custom"]["enabled"] is False

    def test_typo_tag_query_resolves_to_single_candidate(self, monkeypatch, tmp_path):
        code, _original, updated = run_enrich(
            monkeypatch,
            tmp_path,
            {},
            input_lines=["", "", "", "", "", "", "", "", "chroes", "home"],
        )

        assert code is None
        assert updated["tags"] == ["chores"]
        assert updated["focus_domain"] is None

    def test_ambiguous_tag_query_asks_for_choice(self, monkeypatch):
        inputs = iter(["2"])
        monkeypatch.setattr(enrich, "_readline", lambda _prompt: next(inputs))

        selected = enrich.resolve_tag_input("chroes", ["chores", "chroesx"])

        assert selected == "chores"
