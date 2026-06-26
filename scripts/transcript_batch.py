#!/usr/bin/env python3

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from jsonschema import ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from metadata.rewrite import (  # noqa: E402
    patch_existing_metadata_atomic,
)
from schema_validation import validate_document  # noqa: E402
from metadata.writer import write_json_atomic  # noqa: E402


TRANSCRIPT_SCHEMA_PATH = ROOT_DIR / "schemas" / "transcript.v1.schema.json"
TRANSLATION_SCHEMA_PATH = ROOT_DIR / "schemas" / "translation.v1.schema.json"
TRANSCRIPT_SCHEMA = json.loads(TRANSCRIPT_SCHEMA_PATH.read_text())
TRANSLATION_SCHEMA = json.loads(TRANSLATION_SCHEMA_PATH.read_text())
DEFAULT_VLOG_DIR = ROOT_DIR / "vlog"
DEFAULT_MODEL = Path("~/whisper_models/ggml-large-v3.bin").expanduser()
DEFAULT_SOURCE_LABEL = "whisper-large-v3-source"
DEFAULT_TARGET_LABEL = "whisper-large-v3-translate-en"
TRANSCRIBE_ALLOWED_UPDATES = frozenset({"transcript_file", "metadata_quality"})


class TranscriptValidationError(ValueError):
    pass


class TranslationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Candidate:
    stem: str
    media_path: Path
    metadata_path: Path
    transcript_rel: str
    transcript_path: Path
    linked_transcript_path: Path | None
    action: str
    reason: str


@dataclass(frozen=True)
class TranslationCandidate:
    stem: str
    media_path: Path
    source_path: Path
    target_path: Path
    action: str
    reason: str


def transcript_relative_path(stem: str, model_label: str) -> str:
    if not model_label or Path(model_label).name != model_label:
        raise ValueError("model_label must be a non-empty filename component")
    return f"transcripts/{stem}.{model_label}.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def resolve_existing_transcript(vlog_dir: Path, transcript_file: str) -> Path:
    path = Path(transcript_file)
    return path if path.is_absolute() else vlog_dir / path


def validate_transcript_payload(
    payload: dict, *, media_duration_ms: int | None = None, tolerance_ms: int = 15000
) -> None:
    if not isinstance(payload, dict):
        raise TranscriptValidationError("transcript must be a JSON object")

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

    try:
        validate_document(payload, TRANSCRIPT_SCHEMA)
    except ValidationError as exc:
        raise TranscriptValidationError(
            f"transcript schema validation failed: {exc}"
        ) from exc


def validate_transcript_file(
    path: Path, *, media_duration_ms: int | None = None
) -> None:
    validate_transcript_payload(load_json(path), media_duration_ms=media_duration_ms)


def discover_transcription_candidates(
    vlog_dir: Path, *, model_label: str
) -> list[Candidate]:
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
        linked_transcript_path = None

        if not metadata_path.exists():
            action = "missing_metadata"
            reason = "metadata JSON is missing"
        else:
            try:
                metadata = load_json(metadata_path)
            except (json.JSONDecodeError, OSError) as exc:
                action = "invalid_metadata"
                reason = f"metadata JSON is unreadable: {exc}"
                metadata = None

            if not isinstance(metadata, dict):
                action = "invalid_metadata"
                reason = "metadata must be a JSON object"
            elif metadata.get("id") != stem:
                action = "identity_mismatch"
                reason = f"metadata id does not match media stem {stem}"
            elif metadata.get("media_file") != media_path.name:
                action = "identity_mismatch"
                reason = f"metadata media_file does not match {media_path.name}"
            elif metadata.get("metadata_quality") not in {
                "basic",
                "full",
                "corrected",
                "bad",
            }:
                action = "invalid_metadata"
                reason = "metadata_quality is missing or unknown"
            elif metadata.get("metadata_quality") == "bad":
                action = "skip_bad"
                reason = "metadata_quality is bad"
            elif metadata.get("transcript_file") is not None:
                transcript_file = metadata["transcript_file"]
                if not isinstance(transcript_file, str):
                    action = "invalid_metadata"
                    reason = "transcript_file must be a string or null"
                    existing_path = None
                else:
                    existing_path = resolve_existing_transcript(
                        vlog_dir, transcript_file
                    )

                transcript_root = (vlog_dir / "transcripts").resolve()
                if existing_path is not None:
                    try:
                        existing_path.resolve().relative_to(transcript_root)
                    except ValueError:
                        action = "invalid_transcript_link"
                        reason = "transcript_file must resolve inside vlog/transcripts"
                        existing_path = None

                linked_transcript_path = existing_path
                if existing_path is None:
                    pass
                elif existing_path.exists():
                    try:
                        validate_transcript_file(existing_path)
                    except (
                        json.JSONDecodeError,
                        OSError,
                        TranscriptValidationError,
                    ) as exc:
                        action = "invalid_linked_transcript"
                        reason = f"linked transcript is invalid: {exc}"
                    else:
                        action = "skip_linked"
                        reason = "metadata points to a structurally valid transcript"
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
                linked_transcript_path=linked_transcript_path,
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
    translate: bool = False,
) -> Path:
    command = [
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
    ]
    if translate:
        command.append("-tr")
    command.extend(["-oj", "-of", str(output_base), str(wav_path)])
    subprocess.run(command, check=True)
    return Path(f"{output_base}.json")


def promoted_quality(current_quality: str) -> str:
    if current_quality == "bad":
        raise ValueError("bad metadata cannot be promoted by transcription")
    if current_quality == "basic":
        return "full"
    if current_quality in {"full", "corrected"}:
        return current_quality
    raise ValueError("metadata_quality is missing or unknown")


def validate_metadata_identity(metadata: dict, candidate: Candidate) -> None:
    if metadata.get("id") != candidate.stem:
        raise ValueError(f"metadata id does not match media stem {candidate.stem}")
    if metadata.get("media_file") != candidate.media_path.name:
        raise ValueError(
            f"metadata media_file does not match {candidate.media_path.name}"
        )


def link_transcript(candidate: Candidate) -> None:
    metadata = load_json(candidate.metadata_path)
    validate_metadata_identity(metadata, candidate)
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
        write_json_atomic(candidate.transcript_path, load_json(transcript_tmp))

    link_transcript(candidate)


def process_transcription_candidate(candidate: Candidate, *, args) -> str:
    if candidate.action in {
        "missing_metadata",
        "invalid_metadata",
        "identity_mismatch",
        "skip_bad",
        "invalid_transcript_link",
        "invalid_linked_transcript",
        "repair_needed",
        "invalid_existing_transcript",
    }:
        return f"{candidate.action}: {candidate.stem}: {candidate.reason}"

    if candidate.action == "skip_linked":
        if candidate.linked_transcript_path is None:
            raise ValueError("linked transcript path is missing")
        duration_ms = media_duration_ms(candidate.media_path, ffprobe=args.ffprobe)
        try:
            validate_transcript_file(
                candidate.linked_transcript_path,
                media_duration_ms=duration_ms,
            )
        except (json.JSONDecodeError, OSError, TranscriptValidationError) as exc:
            return f"invalid_linked_transcript: {candidate.stem}: {exc}"
        return f"skip_linked: {candidate.stem}: linked transcript is valid"

    if not args.apply:
        return f"dry_run: {candidate.stem}: would {candidate.action}"

    if candidate.action == "link_existing":
        duration_ms = media_duration_ms(candidate.media_path, ffprobe=args.ffprobe)
        validate_transcript_file(
            candidate.transcript_path, media_duration_ms=duration_ms
        )
        link_transcript(candidate)
        return f"linked: {candidate.stem}: {candidate.transcript_rel}"

    if candidate.action == "transcribe":
        transcribe_candidate(
            candidate,
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


def validate_source_transcript(payload: dict) -> list[dict]:
    try:
        validate_transcript_payload(payload)
    except TranscriptValidationError as exc:
        raise TranslationValidationError(str(exc)) from exc
    return payload["transcription"]


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_translation_sidecar(payload: dict) -> None:
    try:
        validate_document(payload, TRANSLATION_SCHEMA)
    except ValidationError as exc:
        raise TranslationValidationError(
            f"translation schema validation failed: {exc}"
        ) from exc

    source_shape = {
        "result": {"language": payload["result"]["language"]},
        "transcription": [
            {
                "timestamps": segment["timestamps"],
                "offsets": segment["offsets"],
                "text": segment["text"],
            }
            for segment in payload["transcription"]
        ],
    }
    try:
        validate_transcript_payload(source_shape)
    except TranscriptValidationError as exc:
        raise TranslationValidationError(str(exc)) from exc


def validate_translation_provenance(
    payload: dict, *, source_path: Path, expected_sha256: str
) -> None:
    validate_translation_sidecar(payload)
    translation = payload["translation"]
    if translation["source_file"] != source_path.name:
        raise TranslationValidationError(
            "translation source_file does not match source transcript"
        )
    if translation["source_sha256"] != expected_sha256:
        raise TranslationValidationError(
            "translation source_sha256 does not match source transcript"
        )


def discover_translation_candidates(
    vlog_dir: Path, *, source_label: str, target_label: str
) -> list[TranslationCandidate]:
    if not source_label or Path(source_label).name != source_label:
        raise ValueError("source_label must be a non-empty filename component")
    if not target_label or Path(target_label).name != target_label:
        raise ValueError("target_label must be a non-empty filename component")

    transcript_dir = vlog_dir / "transcripts"
    source_paths = sorted(transcript_dir.glob(f"*.{source_label}.json"))
    candidates = []
    for source_path in source_paths:
        stem = source_path.name.removesuffix(f".{source_label}.json")
        media_paths = [
            path
            for suffix in (".mkv", ".mov")
            if (path := vlog_dir / f"{stem}{suffix}").exists()
        ]
        target_path = transcript_dir / f"{stem}.{target_label}.json"

        if len(media_paths) != 1:
            action = "invalid_media"
            reason = "expected exactly one matching .mkv or .mov media file"
            media_path = media_paths[0] if media_paths else vlog_dir / f"{stem}.missing"
        else:
            media_path = media_paths[0]
            try:
                validate_source_transcript(load_json(source_path))
            except (json.JSONDecodeError, OSError, TranslationValidationError) as exc:
                action = "invalid_source"
                reason = str(exc)
            else:
                if not target_path.exists():
                    action = "translate"
                    reason = (
                        "source transcript and media are ready for Whisper translation"
                    )
                else:
                    try:
                        validate_translation_provenance(
                            load_json(target_path),
                            source_path=source_path,
                            expected_sha256=source_sha256(source_path),
                        )
                    except (
                        json.JSONDecodeError,
                        OSError,
                        TranslationValidationError,
                    ) as exc:
                        action = "stale_existing"
                        reason = str(exc)
                    else:
                        action = "skip_existing"
                        reason = "translated transcript matches source transcript"

        candidates.append(
            TranslationCandidate(
                stem=stem,
                media_path=media_path,
                source_path=source_path,
                target_path=target_path,
                action=action,
                reason=reason,
            )
        )

    return candidates


def overlapping_source_text(source_segments: list[dict], translated: dict) -> str:
    start = translated["offsets"]["from"]
    end = translated["offsets"]["to"]
    return " ".join(
        segment["text"].strip()
        for segment in source_segments
        if segment["offsets"]["from"] < end and segment["offsets"]["to"] > start
    )


def build_translated_payload(
    source_payload: dict,
    *,
    source_path: Path,
    source_hash: str,
    raw_translation: dict,
) -> dict:
    source_segments = source_payload["transcription"]
    translated_segments = []
    for segment in raw_translation["transcription"]:
        translated = dict(segment)
        translated["source_text"] = overlapping_source_text(source_segments, segment)
        translated_segments.append(translated)

    return {
        "result": {
            "language": "en",
            "source_language": source_payload["result"]["language"],
        },
        "translation": {
            "source_file": source_path.name,
            "source_sha256": source_hash,
            "target_language": "en",
        },
        "transcription": translated_segments,
    }


def translate_candidate(
    candidate: TranslationCandidate,
    *,
    ffmpeg: str,
    ffprobe: str,
    whisper_cli: str,
    model: Path,
    target_label: str,
    threads: int,
    tmp_dir: Path | None,
) -> None:
    source_bytes = candidate.source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    source_payload = json.loads(source_bytes)
    validate_source_transcript(source_payload)

    with tempfile.TemporaryDirectory(dir=tmp_dir) as work_dir_name:
        work_dir = Path(work_dir_name)
        wav_path = work_dir / f"{candidate.stem}.translate.wav"
        output_base = work_dir / f"{candidate.stem}.{target_label}"
        extract_wav(candidate.media_path, wav_path, ffmpeg=ffmpeg)
        raw_translation_path = run_whisper(
            wav_path,
            output_base,
            whisper_cli=whisper_cli,
            model=model,
            threads=threads,
            translate=True,
        )
        duration_ms = media_duration_ms(candidate.media_path, ffprobe=ffprobe)
        validate_transcript_file(raw_translation_path, media_duration_ms=duration_ms)
        raw_translation = load_json(raw_translation_path)

    payload = build_translated_payload(
        source_payload,
        source_path=candidate.source_path,
        source_hash=source_hash,
        raw_translation=raw_translation,
    )
    validate_translation_sidecar(payload)
    if candidate.target_path.exists():
        raise FileExistsError(candidate.target_path)
    write_json_atomic(candidate.target_path, payload)


def process_translation_candidate(candidate: TranslationCandidate, *, args) -> str:
    if candidate.action in {
        "invalid_media",
        "invalid_source",
        "skip_existing",
        "stale_existing",
    }:
        return f"{candidate.action}: {candidate.stem}: {candidate.reason}"
    if not args.apply:
        return f"dry_run: {candidate.stem}: would translate"
    if candidate.action != "translate":
        raise ValueError(f"unknown action: {candidate.action}")

    translate_candidate(
        candidate,
        ffmpeg=args.ffmpeg,
        ffprobe=args.ffprobe,
        whisper_cli=args.whisper_cli,
        model=args.model,
        target_label=args.target_label,
        threads=args.threads,
        tmp_dir=args.tmp_dir,
    )
    return f"translated: {candidate.stem}: {candidate.target_path.name}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch source transcription and English translation with whisper-cli."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    def add_common_args(command: argparse.ArgumentParser) -> None:
        command.add_argument("--vlog-dir", type=Path, default=DEFAULT_VLOG_DIR)
        command.add_argument("--model", type=Path, default=DEFAULT_MODEL)
        command.add_argument("--ffmpeg", default="ffmpeg")
        command.add_argument("--ffprobe", default="ffprobe")
        command.add_argument("--whisper-cli", default="whisper-cli")
        command.add_argument("--threads", type=int, default=10)
        command.add_argument("--tmp-dir", type=Path, default=None)
        command.add_argument(
            "--apply",
            action="store_true",
            help="write sidecars; default is dry-run",
        )

    transcribe_parser = subparsers.add_parser(
        "transcribe", help="create source-language transcript sidecars"
    )
    add_common_args(transcribe_parser)
    transcribe_parser.add_argument("--model-label", default=DEFAULT_SOURCE_LABEL)

    translate_parser = subparsers.add_parser(
        "translate", help="create English transcript sidecars with Whisper -tr"
    )
    add_common_args(translate_parser)
    translate_parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    translate_parser.add_argument("--target-label", default=DEFAULT_TARGET_LABEL)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.mode == "transcribe":
        candidates = discover_transcription_candidates(
            args.vlog_dir, model_label=args.model_label
        )
        for candidate in candidates:
            print(process_transcription_candidate(candidate, args=args))
    else:
        candidates = discover_translation_candidates(
            args.vlog_dir,
            source_label=args.source_label,
            target_label=args.target_label,
        )
        for candidate in candidates:
            print(process_translation_candidate(candidate, args=args))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
