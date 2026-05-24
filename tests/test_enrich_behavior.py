import json

import pytest

import scripts.enrich as enrich


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

    def test_tag_overflow_reprompts_and_leaves_tags_unchanged(self, monkeypatch, tmp_path):
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
