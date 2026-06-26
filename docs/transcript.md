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

`scripts/transcript_batch.py transcribe` scans `vlog/` for good `.mkv` and `.mov` media files.

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

Source transcription does not use `-tr`; English translation is an explicit second mode.

## Transcript Validation

Before a transcript sidecar is promoted, the batch script checks:

- JSON parses
- `transcription` is a non-empty list
- every segment has integer `offsets.from` and `offsets.to`
- each segment has positive duration
- segment offsets do not overlap
- final transcript timestamp is close to media duration
- payload shape satisfies `schemas/transcript.v1.schema.json`
- metadata `id` matches the media stem
- metadata `media_file` matches the exact media filename

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

The relational identity checks happen before linking. They do not mutate or normalize pre-existing metadata.

## Existing Sidecars

If a source transcript sidecar already exists and `TS.json.transcript_file` is still `null`, rerunning transcription with `--apply` validates and links the existing sidecar instead of rerunning Whisper.

Already-linked sidecars are schema-validated before they are skipped. Both linked and unlinked existing sidecars are checked against media duration before a link is accepted.

```bash
PYTHONPATH=. python3 scripts/transcript_batch.py transcribe \
  --vlog-dir /Volumes/groot/dev/privledger/vlog \
  --apply
```

## Translation

Translation is a separate mode in the same batch command:

```text
media file + validated source transcript
-> temporary 16 kHz mono WAV
-> whisper-cli -tr English JSON
-> validated translated transcript sidecar
```

Run it with:

```bash
PYTHONPATH=. python3 scripts/transcript_batch.py translate \
  --vlog-dir /Volumes/groot/dev/privledger/vlog \
  --apply
```

The output is:

```text
vlog/transcripts/TS.whisper-large-v3-translate-en.json
```

Whisper translation may use segment boundaries that differ from source transcription. Translated segments keep Whisper's translated timestamps and offsets, while `source_text` contains source segments whose time ranges overlap the translated segment.

Translation does not update `TS.json`.

Each translated sidecar stores `translation.source_sha256`, the SHA-256 hash of the exact source transcript bytes. Existing translations with a missing or mismatched hash are reported as `stale_existing`.

## Validation Boundary

There are two metadata write paths:

- full metadata writes: validate all stored-data invariants and schema shape
- transcript link patches: validate only transcript-owned fields and preserve unrelated existing metadata

Both paths use the atomic JSON write primitive in `metadata/writer.py`.


Source and translated sidecars are published through the same atomic JSON writer. `transcript.v1.schema.json` and `translation.v1.schema.json` validate individual sidecar structure; Python checks cross-segment timing and relationships among media, metadata, source transcripts, and translations.
