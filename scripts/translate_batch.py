#!/usr/bin/env python3

import argparse
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_VLOG_DIR = ROOT_DIR / "vlog"
DEFAULT_SOURCE_LABEL = "whisper-large-v3-source"
DEFAULT_TARGET_LABEL = "whisper-large-v3-translate-en"


class TranslationError(ValueError):
    pass


@dataclass(frozen=True)
class TranslationCandidate:
    source_path: Path
    target_path: Path
    action: str
    reason: str


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def validate_source_transcript(payload: dict) -> list[dict]:
    segments = payload.get("transcription")
    if not isinstance(segments, list) or not segments:
        raise TranslationError("transcription must be a non-empty list")

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise TranslationError(f"segment {index} must be an object")
        if not isinstance(segment.get("text"), str):
            raise TranslationError(f"segment {index} text must be a string")
        if not isinstance(segment.get("timestamps"), dict):
            raise TranslationError(f"segment {index} timestamps must be an object")
        offsets = segment.get("offsets")
        if not isinstance(offsets, dict):
            raise TranslationError(f"segment {index} offsets must be an object")

    return segments


def validate_translation_payload(payload: dict, expected_count: int) -> list[str]:
    texts = payload.get("texts")
    if not isinstance(texts, list) or len(texts) != expected_count:
        raise TranslationError("translator must return one text per input text")
    if not all(isinstance(text, str) and text.strip() for text in texts):
        raise TranslationError("translated texts must be non-empty strings")
    return texts


def discover_candidates(
    vlog_dir: Path, *, source_label: str, target_label: str
) -> list[TranslationCandidate]:
    transcript_dir = vlog_dir / "transcripts"
    source_paths = sorted(transcript_dir.glob(f"*.{source_label}.json"))
    candidates = []

    for source_path in source_paths:
        target_path = source_path.with_name(
            source_path.name.removesuffix(f".{source_label}.json")
            + f".{target_label}.json"
        )
        if target_path.exists():
            action = "skip_existing"
            reason = "translated transcript already exists"
        else:
            try:
                validate_source_transcript(load_json(source_path))
            except (json.JSONDecodeError, TranslationError) as exc:
                action = "invalid_source"
                reason = str(exc)
            else:
                action = "translate"
                reason = "source transcript is ready for translation"

        candidates.append(
            TranslationCandidate(
                source_path=source_path,
                target_path=target_path,
                action=action,
                reason=reason,
            )
        )

    return candidates


def run_translator_command(
    command: str, texts: list[str], *, target_language: str
) -> list[str]:
    payload = json.dumps(
        {"target_language": target_language, "texts": texts},
        ensure_ascii=False,
    )
    result = subprocess.run(
        shlex.split(command),
        input=payload,
        capture_output=True,
        text=True,
        check=True,
    )
    return validate_translation_payload(json.loads(result.stdout), len(texts))


def translate_segments(
    segments: list[dict],
    *,
    translator_cmd: str,
    target_language: str,
    batch_size: int,
) -> list[dict]:
    translated_segments = []
    for start in range(0, len(segments), batch_size):
        batch = segments[start : start + batch_size]
        translated_texts = run_translator_command(
            translator_cmd,
            [segment["text"] for segment in batch],
            target_language=target_language,
        )
        for segment, translated_text in zip(batch, translated_texts, strict=True):
            translated = dict(segment)
            translated["source_text"] = segment["text"]
            translated["text"] = translated_text
            translated_segments.append(translated)

    return translated_segments


def build_translated_payload(
    source_payload: dict,
    *,
    source_path: Path,
    target_language: str,
    translated_segments: list[dict],
) -> dict:
    return {
        "result": {
            "language": target_language,
            "source_language": source_payload.get("result", {}).get("language"),
        },
        "translation": {
            "source_file": source_path.name,
            "target_language": target_language,
        },
        "transcription": translated_segments,
    }


def translate_candidate(
    candidate: TranslationCandidate,
    *,
    translator_cmd: str,
    target_language: str,
    batch_size: int,
) -> None:
    source_payload = load_json(candidate.source_path)
    segments = validate_source_transcript(source_payload)
    translated_segments = translate_segments(
        segments,
        translator_cmd=translator_cmd,
        target_language=target_language,
        batch_size=batch_size,
    )
    payload = build_translated_payload(
        source_payload,
        source_path=candidate.source_path,
        target_language=target_language,
        translated_segments=translated_segments,
    )

    candidate.target_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    )


def process_candidate(candidate: TranslationCandidate, *, args) -> str:
    if candidate.action in {"skip_existing", "invalid_source"}:
        return f"{candidate.action}: {candidate.source_path.name}: {candidate.reason}"

    if not args.apply:
        return f"dry_run: {candidate.source_path.name}: would translate"

    if not args.translator_cmd:
        return (
            f"missing_translator: {candidate.source_path.name}: "
            "--translator-cmd is required with --apply"
        )

    translate_candidate(
        candidate,
        translator_cmd=args.translator_cmd,
        target_language=args.target_language,
        batch_size=args.batch_size,
    )
    return f"translated: {candidate.source_path.name}: {candidate.target_path.name}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch translate source Whisper transcripts while preserving timestamps."
    )
    parser.add_argument("--vlog-dir", type=Path, default=DEFAULT_VLOG_DIR)
    parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--target-label", default=DEFAULT_TARGET_LABEL)
    parser.add_argument("--target-language", default="en")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument(
        "--translator-cmd",
        help=(
            "Command that reads JSON {'target_language','texts'} from stdin and "
            "writes JSON {'texts':[...]} to stdout."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write translated transcript sidecars; default is dry-run",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    candidates = discover_candidates(
        args.vlog_dir,
        source_label=args.source_label,
        target_label=args.target_label,
    )
    for candidate in candidates:
        print(process_candidate(candidate, args=args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
