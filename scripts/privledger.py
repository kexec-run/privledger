#!/usr/bin/env python3

import json
import os
import platform
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from metadata.check import check_invariants  # noqa: E402
from metadata.writer import write_metadata_atomic  # noqa: E402

CONFIG_ENV = ROOT_DIR / "config" / "env"
SCHEMA_PATH = ROOT_DIR / "tests" / "schema" / "metadata.v1.schema.json"
CUSTOM_SCHEMA_PATH = ROOT_DIR / "config" / "custom_schema.yaml"

proc: subprocess.Popen | None = None


@dataclass(frozen=True)
class RecorderConfig:
    name: str
    record_script: Path
    good_suffix: str
    bad_suffix: str
    required_env_vars: tuple[str, ...]
    video_device_env: str | None = None
    default_video_device: str = "unknown"


def linux_config() -> RecorderConfig:
    return RecorderConfig(
        name="privledger-linux",
        record_script=ROOT_DIR / "scripts" / "record-linux.sh",
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


def mac_config() -> RecorderConfig:
    return RecorderConfig(
        name="privledger-mac",
        record_script=ROOT_DIR / "scripts" / "record-mac.sh",
        good_suffix=".mov",
        bad_suffix=".mov.bad.mov",
        required_env_vars=(
            "SCHEMA_VERSION",
            "PIPELINE_VERSION",
        ),
        video_device_env="AVCAM_CAMERA",
        default_video_device="Brio",
    )


def load_config_env(config: RecorderConfig) -> tuple[dict, str, str]:
    if not CONFIG_ENV.exists():
        print(
            f"[{config.name}] ERROR: config/env missing (copy from config/env.sample)",
            file=sys.stderr,
        )
        sys.exit(1)

    load_dotenv(CONFIG_ENV)

    schema_version = os.getenv("SCHEMA_VERSION")
    pipeline_version = os.getenv("PIPELINE_VERSION")

    if not schema_version or not pipeline_version:
        print(f"[{config.name}] ERROR: missing required env values", file=sys.stderr)
        sys.exit(1)

    env = os.environ.copy()
    missing = [key for key in config.required_env_vars if not env.get(key)]
    if missing:
        print(
            f"[{config.name}] ERROR: missing required env vars: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    return env, schema_version, pipeline_version


def load_schema(config: RecorderConfig) -> dict:
    if not SCHEMA_PATH.exists():
        print(f"[{config.name}] ERROR: schema file missing", file=sys.stderr)
        sys.exit(1)
    return json.loads(SCHEMA_PATH.read_text())


def load_custom_schema():
    custom_enabled = os.getenv("CUSTOM_ENABLED", "false").lower() == "true"
    custom_fields = None

    if custom_enabled:
        try:
            from metadata.custom_schema import (
                load_custom_schema as load_custom_schema_file,
            )

            custom_fields, _, _ = load_custom_schema_file(CUSTOM_SCHEMA_PATH)
        except FileNotFoundError:
            custom_enabled = False
            custom_fields = None
        except ValueError as e:
            print(f"[privledger] ERROR: invalid custom schema: {e}", file=sys.stderr)
            sys.exit(1)

    return custom_enabled, custom_fields


def detect_video_device_name(config: RecorderConfig, env: dict) -> str:
    if not config.video_device_env:
        return config.default_video_device.lower()

    raw_value = env.get(config.video_device_env, config.default_video_device)

    if config.video_device_env == "VIDEO_DEV":
        try:
            node = os.path.basename(os.path.realpath(raw_value))
            name = (
                Path(f"/sys/class/video4linux/{node}/name").read_text().strip().lower()
            )
            return name if name else "unknown"
        except Exception:
            return "unknown"

    value = raw_value.strip().lower()
    return value if value else config.default_video_device.lower()


def handle_signal(signum, frame):
    if proc and proc.poll() is None:
        print("[privledger] Forwarding SIGINT to recorder...", flush=True)
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGINT)
        except ProcessLookupError:
            pass


def classify_artifact(config: RecorderConfig, timestamp: str):
    good_path = ROOT_DIR / "vlog" / f"{timestamp}{config.good_suffix}"
    bad_path = ROOT_DIR / "vlog" / f"{timestamp}{config.bad_suffix}"

    good_exists = good_path.exists()
    bad_exists = bad_path.exists()

    if good_exists and bad_exists:
        print(
            f"[{config.name}] FATAL: both good and bad artifacts exist - pipeline invariant violated",
            file=sys.stderr,
        )
        sys.exit(2)

    if not good_exists and not bad_exists:
        return None, None

    if good_exists:
        return good_path, "basic"

    return bad_path, "bad"


def run_enrichment(metadata_path: Path):
    enrich_script = ROOT_DIR / "scripts" / "enrich.py"
    if not enrich_script.exists():
        print("[privledger] ERROR: enrich.py not found", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run([sys.executable, str(enrich_script), str(metadata_path)])
    if result.returncode != 0:
        print(
            f"[privledger] ERROR: enrich.py failed with exit {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(result.returncode)


def supervise_capture(config: RecorderConfig, enrich_after_record: bool = False):
    global proc

    env, schema_version, pipeline_version = load_config_env(config)
    schema = load_schema(config)
    custom_enabled, custom_fields = load_custom_schema()

    if not config.record_script.exists():
        print(
            f"[{config.name}] ERROR: {config.record_script.name} not found",
            file=sys.stderr,
        )
        sys.exit(1)

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d-%H%M")
    timestamp_utc_iso = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    timestamp_local_iso = now.astimezone().replace(microsecond=0).isoformat()
    env["TIMESTAMP"] = timestamp

    print(f"[{config.name}] Starting capture at {timestamp}...", flush=True)

    try:
        proc = subprocess.Popen(
            [str(config.record_script)],
            env=env,
            start_new_session=True,
        )

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        exit_code = proc.wait()

    except KeyboardInterrupt:
        handle_signal(signal.SIGINT, None)
        exit_code = proc.wait()

    media_path, metadata_quality = classify_artifact(config, timestamp)
    if media_path is None:
        print(
            f"[{config.name}] ERROR: no media artifact found for {timestamp} - preflight or early failure",
            file=sys.stderr,
        )
        sys.exit(exit_code if exit_code != 0 else 1)

    metadata_path = ROOT_DIR / "vlog" / f"{timestamp}.json"
    optional_fields = {
        "timestamp_local": timestamp_local_iso,
        "video_device": detect_video_device_name(config, env),
    }

    if custom_enabled:
        optional_fields["custom"] = None

    try:
        if custom_enabled:
            check_invariants(
                {"custom": optional_fields.get("custom")},
                custom_fields,
            )

        written = write_metadata_atomic(
            output_path=metadata_path,
            entry_id=timestamp,
            timestamp_utc=timestamp_utc_iso,
            media_file=media_path.name,
            metadata_quality=metadata_quality,
            schema_version=int(schema_version),
            pipeline_version=pipeline_version,
            optional_fields=optional_fields,
            schema=schema,
        )
        print(f"[{config.name}] Metadata written -> {written.name}", flush=True)
    except Exception as e:
        print(f"[{config.name}] ERROR: metadata write failed: {e}", file=sys.stderr)
        sys.exit(1)

    if metadata_quality == "bad" and exit_code == 0:
        exit_code = 1

    if exit_code != 0:
        print(
            f"[{config.name}] Capture finished with bad artifact (exit {exit_code})",
            file=sys.stderr,
        )
        sys.exit(exit_code)

    if enrich_after_record:
        run_enrichment(metadata_path)

    print(f"[{config.name}] Capture finished cleanly.", flush=True)
    sys.exit(0)


def main():
    args = sys.argv[1:]
    allowed_args = {"--enrich"}
    unknown_args = [arg for arg in args if arg not in allowed_args]
    if unknown_args:
        print(
            f"Usage: privledger.py [--enrich]\nUnknown argument: {unknown_args[0]}",
            file=sys.stderr,
        )
        sys.exit(1)

    enrich_after_record = "--enrich" in args

    if platform.system() == "Darwin":
        supervise_capture(mac_config(), enrich_after_record=enrich_after_record)
    else:
        supervise_capture(linux_config(), enrich_after_record=enrich_after_record)


if __name__ == "__main__":
    main()
