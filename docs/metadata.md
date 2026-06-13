# Metadata

This doc covers metadata shape, validation, persistence, and stored-data invariants.

For tag meaning and vocabulary semantics, see [tags.md](./tags.md).
For prompt behavior and typo handling, see [enrichment.md](./enrichment.md).

## Metadata Lifecycle

```text
capture classification
-> metadata/writer.py
-> metadata/check.py
-> metadata/validator.py
-> atomic JSON write
```

`metadata/writer.py` builds the metadata object, runs core invariant checks, validates against JSON schema, and writes the final file atomically.

## Field Groups

Required schema-enforced fields:

- `id`
- `timestamp_utc`
- `schema_version`
- `pipeline_version`
- `metadata_quality`
- `media_file`

Auto-populated capture fields:

- `timestamp_local`
- `video_device`

Nullable user-populated fields:

- `mood`
- `energy`
- `stress`
- `sleepiness`
- `sleep_hours`
- `caffeine_mg`
- `body_weight`
- `focus_domain`
- `tags`
- `location`

Deferred fields:

- `transcript_file`

## Validation Layers

| Layer | File | Owns |
|---|---|---|
| tag/focus predicates | `metadata/tags.py` | vocabulary loading, regular tag checks, focus-domain checks |
| semantic invariants | `metadata/check.py` | stored-data validation before schema validation |
| custom schema loading | `metadata/custom_schema.py` | YAML field/type normalization and schema hash generation |
| schema validation | `metadata/validator.py` | JSON schema enforcement |
| persistence | `metadata/writer.py` | construction, validation order, atomic write |

## Stored-Data Invariants

Stored JSON must contain canonical values only.

Tag invariants:

- `tags` may be `null` or a list; `null` normalizes to `[]`
- every regular tag must be a string
- every regular tag must be lowercase
- every regular tag must exist in `config/tags.txt`
- regular tags must be unique
- regular tags must have at most 5 values

Focus-domain invariants:

- `focus_domain` may be `null`
- non-null `focus_domain` must be a string
- non-null `focus_domain` must be lowercase
- non-null `focus_domain` must exist in `config/tags.txt`
- non-null `focus_domain` must not appear in regular `tags`

Numeric invariants:

- `mood`, `energy`, `stress`, and `sleepiness` are `null` or `1..5`
- `sleep_hours`, `caffeine_mg`, and `body_weight` are `null` or non-negative

Schema invariants:

- required fields must exist
- unknown fields are rejected
- enum fields must use known values
- `transcript_file` is `null` or a non-empty string

Custom metadata invariants:

- when `CUSTOM_ENABLED=false`, capture metadata omits `custom`
- when `CUSTOM_ENABLED=true`, initial capture metadata includes `custom: null`
- malformed `config/custom_schema.yaml` fails before recording starts with a clean Privledger error
- enriched custom metadata must use the active schema envelope: `{"schema_hash": "...", "data": {...}}`

## Tag Helper Boundary

`metadata/tags.py` is the source of truth for exact tag/focus predicates.

Callers may handle failures differently:

- `scripts/enrich.py` catches validation errors and re-prompts
- `metadata/check.py` lets validation errors block writes

Callers should not reimplement exact tag/focus rules locally.

## Atomic Write Contract

Metadata writes should leave either:

- the previous valid file intact, or
- the complete new valid file in place

Partial metadata files should not become durable state.
