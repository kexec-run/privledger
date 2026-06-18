#!/usr/bin/env python3

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from metadata.rewrite import (  # noqa: E402
    patch_existing_metadata_atomic,
)


SCHEMA_PATH = ROOT_DIR / "tests" / "schema" / "metadata.v1.schema.json"
DEFAULT_VLOG_DIR = ROOT_DIR / "vlog"
DEFAULT_MODEL = Path("~/whisper_models/ggml-large-v3.bin").expanduser()
DEFAULT_MODEL_LABEL = "whisper-large-v3-source"
TRANSCRIBE_ALLOWED_UPDATES = frozenset({"transcript_file", "metadata_quality"})


class TranscriptValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    stem: str
    media_path: Path
    metadata_path: Path
    transcript_rel: str
    transcript_path: Path
    action: str
    reason: str


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def transcript_relative_path(stem: str, model_label: str) -> str:
    return f"transcripts/{stem}.{model_label}.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def resolve_existing_transcript(vlog_dir: Path, transcript_file: str) -> Path:
    path = Path(transcript_file)
    return path if path.is_absolute() else vlog_dir / path


def validate_transcript_payload(
    payload: dict, *, media_duration_ms: int | None = None, tolerance_ms: int = 15000
) -> None:
    segments = payload.get("transcription")
    if not isinstance(segments, list) or not segments:
        raise TranscriptValidationError("transcription must be a non-empty list")

    previous_to = -1
    last_to = None
    for index, segment in enumerate(segments):
        offsets = segment.get("offsets") if isinstance(segment, dict) else None
        if not isinstance(offsets, dict):
            raise TranscriptValidationError(f"segment {index} has no offsets object")

        start = offsets.get("from")
        end = offsets.get("to")
        if not isinstance(start, int) or not isinstance(end, int):
            raise TranscriptValidationError(f"segment {index} offsets must be integers")
        if end <= start:
            raise TranscriptValidationError(
                f"segment {index} has non-positive duration"
            )
        if start < previous_to:
            raise TranscriptValidationError(
                f"segment {index} overlaps previous segment"
            )

        previous_to = end
        last_to = end

    if media_duration_ms is not None and last_to is not None:
        delta = abs(media_duration_ms - last_to)
        if delta > tolerance_ms:
            raise TranscriptValidationError(
                f"final transcript timestamp differs from media duration by {delta}ms"
            )


def validate_transcript_file(
    path: Path, *, media_duration_ms: int | None = None
) -> None:
    validate_transcript_payload(load_json(path), media_duration_ms=media_duration_ms)


def discover_candidates(vlog_dir: Path, *, model_label: str) -> list[Candidate]:
    candidates = []
    media_paths = sorted(
        [
            *vlog_dir.glob("*.mkv"),
            *vlog_dir.glob("*.mov"),
        ]
    )

    for media_path in media_paths:
        if ".bad." in media_path.name:
            continue

        stem = media_path.stem
        metadata_path = vlog_dir / f"{stem}.json"
        transcript_rel = transcript_relative_path(stem, model_label)
        transcript_path = vlog_dir / transcript_rel

        if not metadata_path.exists():
            action = "missing_metadata"
            reason = "metadata JSON is missing"
        else:
            metadata = load_json(metadata_path)
            quality = metadata.get("metadata_quality")
            transcript_file = metadata.get("transcript_file")

            if quality == "bad":
                action = "skip_bad"
                reason = "metadata_quality is bad"
            elif transcript_file:
                existing_path = resolve_existing_transcript(vlog_dir, transcript_file)
                if existing_path.exists():
                    action = "skip_linked"
                    reason = "metadata already points to an existing transcript"
                else:
                    action = "repair_needed"
                    reason = "metadata points to a missing transcript"
            elif transcript_path.exists():
                try:
                    validate_transcript_file(transcript_path)
                except (json.JSONDecodeError, TranscriptValidationError) as exc:
                    action = "invalid_existing_transcript"
                    reason = f"existing transcript is invalid: {exc}"
                else:
                    action = "link_existing"
                    reason = "validated existing transcript sidecar"
            else:
                action = "transcribe"
                reason = "no source transcript linked or present"

        candidates.append(
            Candidate(
                stem=stem,
                media_path=media_path,
                metadata_path=metadata_path,
                transcript_rel=transcript_rel,
                transcript_path=transcript_path,
                action=action,
                reason=reason,
            )
        )

    return candidates


def media_duration_ms(media_path: Path, *, ffprobe: str) -> int:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nokey=1:noprint_wrappers=1",
            str(media_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(float(result.stdout.strip()) * 1000)


def extract_wav(media_path: Path, wav_path: Path, *, ffmpeg: str) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-i",
            str(media_path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(wav_path),
        ],
        check=True,
    )


def run_whisper(
    wav_path: Path,
    output_base: Path,
    *,
    whisper_cli: str,
    model: Path,
    threads: int,
) -> Path:
    subprocess.run(
        [
            whisper_cli,
            "-ng",
            "-t",
            str(threads),
            "-mc",
            "0",
            "-nf",
            "-m",
            str(model),
            "-l",
            "auto",
            "-oj",
            "-of",
            str(output_base),
            str(wav_path),
        ],
        check=True,
    )
    return Path(f"{output_base}.json")


def promoted_quality(current_quality: str) -> str:
    if current_quality == "bad":
        raise ValueError("bad metadata cannot be promoted by transcription")
    if current_quality == "basic":
        return "full"
    return current_quality


def link_transcript(
    candidate: Candidate,
    *,
    schema: dict,
) -> None:
    metadata = load_json(candidate.metadata_path)
    updates = {
        "transcript_file": candidate.transcript_rel,
        "metadata_quality": promoted_quality(metadata["metadata_quality"]),
    }
    validate_transcript_metadata_updates(updates)
    patch_existing_metadata_atomic(
        output_path=candidate.metadata_path,
        original=metadata,
        updates=updates,
        allowed_updates=TRANSCRIBE_ALLOWED_UPDATES,
    )


def validate_transcript_metadata_updates(updates: dict) -> None:
    transcript_file = updates.get("transcript_file")
    if not isinstance(transcript_file, str) or not transcript_file:
        raise ValueError("transcript_file must be a non-empty string")

    metadata_quality = updates.get("metadata_quality")
    if metadata_quality not in {"basic", "full", "corrected"}:
        raise ValueError("metadata_quality must be basic, full, or corrected")


def transcribe_candidate(
    candidate: Candidate,
    *,
    schema: dict,
    ffmpeg: str,
    ffprobe: str,
    whisper_cli: str,
    model: Path,
    model_label: str,
    threads: int,
    tmp_dir: Path | None,
) -> None:
    with tempfile.TemporaryDirectory(dir=tmp_dir) as work_dir_name:
        work_dir = Path(work_dir_name)
        wav_path = work_dir / f"{candidate.stem}.whisper.wav"
        output_base = work_dir / f"{candidate.stem}.{model_label}"

        extract_wav(candidate.media_path, wav_path, ffmpeg=ffmpeg)
        transcript_tmp = run_whisper(
            wav_path,
            output_base,
            whisper_cli=whisper_cli,
            model=model,
            threads=threads,
        )
        duration_ms = media_duration_ms(candidate.media_path, ffprobe=ffprobe)
        validate_transcript_file(transcript_tmp, media_duration_ms=duration_ms)

        candidate.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        if candidate.transcript_path.exists():
            raise FileExistsError(candidate.transcript_path)
        shutil.move(str(transcript_tmp), candidate.transcript_path)

    link_transcript(candidate, schema=schema)


def process_candidate(candidate: Candidate, *, args, schema: dict) -> str:
    if candidate.action in {
        "missing_metadata",
        "skip_bad",
        "skip_linked",
        "repair_needed",
        "invalid_existing_transcript",
    }:
        return f"{candidate.action}: {candidate.stem}: {candidate.reason}"

    if not args.apply:
        return f"dry_run: {candidate.stem}: would {candidate.action}"

    if candidate.action == "link_existing":
        link_transcript(candidate, schema=schema)
        return f"linked: {candidate.stem}: {candidate.transcript_rel}"

    if candidate.action == "transcribe":
        transcribe_candidate(
            candidate,
            schema=schema,
            ffmpeg=args.ffmpeg,
            ffprobe=args.ffprobe,
            whisper_cli=args.whisper_cli,
            model=args.model,
            model_label=args.model_label,
            threads=args.threads,
            tmp_dir=args.tmp_dir,
        )
        return f"transcribed: {candidate.stem}: {candidate.transcript_rel}"

    raise ValueError(f"unknown action: {candidate.action}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch transcribe Privledger vlogs in the source language with whisper-cli."
    )
    parser.add_argument("--vlog-dir", type=Path, default=DEFAULT_VLOG_DIR)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--model-label", default=DEFAULT_MODEL_LABEL)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--whisper-cli", default="whisper-cli")
    parser.add_argument("--threads", type=int, default=10)
    parser.add_argument("--tmp-dir", type=Path, default=None)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write transcript sidecars and update metadata; default is dry-run",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    schema = load_schema()
    candidates = discover_candidates(args.vlog_dir, model_label=args.model_label)

    for candidate in candidates:
        print(process_candidate(candidate, args=args, schema=schema))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
