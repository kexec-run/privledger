# Transcripts

This doc covers batch transcript creation, transcript sidecars, metadata linking, and translated transcript artifacts.

For metadata field invariants, see [metadata.md](./metadata.md).

## Artifact Model

Good media artifacts may have transcript sidecars:

```text
vlog/TS.mkv
vlog/TS.json
vlog/transcripts/TS.whisper-large-v3-source.json
vlog/transcripts/TS.whisper-large-v3-translate-en.json
```

`TS.json` stores only a pointer to the source transcript:

```json
"transcript_file": "transcripts/TS.whisper-large-v3-source.json"
```

The full transcript is not embedded in metadata JSON.

## Source Transcription

`scripts/transcribe_batch.py` scans `vlog/` for good `.mkv` and `.mov` media files.

It skips:

- `.bad.*` media artifacts
- records with `metadata_quality=bad`
- metadata that already points to an existing transcript
- metadata that points to a missing transcript, reported as `repair_needed`

For work that needs transcription, it:

```text
media file
-> temporary 16 kHz mono WAV
-> whisper-cli source-language JSON
-> validated transcript sidecar
-> metadata link patch
```

The Whisper command uses source transcription, not direct translation:

```text
whisper-cli -ng -t 10 -mc 0 -nf -l auto -oj
```

Direct Whisper translation with `-tr` is intentionally not used because it makes recognition and translation errors hard to separate.

## Transcript Validation

Before a transcript sidecar is promoted, the batch script checks:

- JSON parses
- `transcription` is a non-empty list
- every segment has integer `offsets.from` and `offsets.to`
- each segment has positive duration
- segment offsets do not overlap
- final transcript timestamp is close to media duration

Invalid transcript sidecars are not linked into metadata.

## Metadata Linking

Transcription owns only:

- `transcript_file`
- `metadata_quality`

When linking succeeds:

```json
"transcript_file": "transcripts/TS.whisper-large-v3-source.json",
"metadata_quality": "full"
```

`metadata_quality` changes as follows:

```text
basic     -> full
full      -> full
corrected -> corrected
bad       -> skipped
```

The transcript linker intentionally does not revalidate unrelated pre-existing metadata such as old tags. It preserves all existing fields and atomically patches only the two transcription-owned fields.

This allows old records with vocabulary drift to receive transcript links without forcing tag cleanup in the same batch operation.

## Existing Sidecars

If a source transcript sidecar already exists and `TS.json.transcript_file` is still `null`, rerunning transcription with `--apply` validates and links the existing sidecar instead of rerunning Whisper.

```bash
PYTHONPATH=. python3 scripts/transcribe_batch.py \
  --vlog-dir /Volumes/groot/dev/privledger/vlog \
  --apply
```

## Translation

Translation is a separate batch stage:

```text
source transcript JSON
-> external translator command
-> English translated transcript JSON
```

`scripts/translate_batch.py` reads source transcript sidecars and writes translated sidecars:

```text
vlog/transcripts/TS.whisper-large-v3-translate-en.json
```

Translated segments preserve source `timestamps` and `offsets`, replace `text` with translated text, and store the original segment text as `source_text`.

Translation does not update `TS.json`.

The translator command must read JSON from stdin:

```json
{"target_language":"en","texts":["..."]}
```

and write JSON to stdout:

```json
{"texts":["translated ..."]}
```

## Validation Boundary

There are two metadata write paths:

- full metadata writes: validate all stored-data invariants and schema shape
- transcript link patches: validate only transcript-owned fields and preserve unrelated existing metadata

Both paths use the atomic JSON write primitive in `metadata/writer.py`.
