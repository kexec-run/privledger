# Enrichment

This doc covers user-driven metadata edits through `scripts/enrich.py`.

For stored-data validation, see [metadata.md](./metadata.md).
For tag semantics, see [tags.md](./tags.md).

## Prompt Flow

`scripts/enrich.py` loads an existing `vlog/TS.json`, prompts for mutable fields, validates the result through `metadata/rewrite.py`, and writes atomically through `metadata/writer.py`.

Current prompt order:

1. ratings
2. body fields
3. tag vocabulary display
4. focus domain
5. regular tags
6. location
7. custom metadata, when enabled

Immutable fields are passed through unchanged.

## Editable Fields

Enrichment may update:

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
- `custom`, when custom schema is enabled

It must not update capture identity fields such as `id`, timestamps, schema versions, pipeline version, media file, metadata quality, or transcript file.

## Input Resolution Boundary

Raw user input is not stored directly when it represents a tag.

Tag input flow:

```text
raw input
-> RapidFuzz or exact resolver
-> canonical tag
-> shared tag/focus validation
-> write JSON
```

Examples:

```text
chroes -> chores
```

If one strong candidate exists, the prompt may resolve automatically.
If multiple plausible candidates exist, the prompt must ask the user to choose.
If no acceptable candidate exists, the prompt must reject and re-prompt.

## Focus Domain Behavior

`focus_domain` is selected from `config/tags.txt`.

It is a primary tag stored separately from regular `tags`.
It must not also appear in regular `tags`.

If the user selects a focus domain that already exists in regular `tags`, enrichment rejects the value and re-prompts. It does not silently remove the regular tag.

If the current JSON already contains a duplicated focus-domain/tag value and the user presses Enter, enrichment rejects the current value and re-prompts.

## Error Behavior

Prompt-level validation should not kill the session when the user can correct the value.

Use re-prompting for:

- invalid numeric input
- unknown tag input
- ambiguous fuzzy tag input
- regular tag overflow
- focus-domain duplication
- focus-domain values outside the configured vocabulary

Abort behavior:

- `KeyboardInterrupt` writes nothing
- write-time validation failure writes no new metadata

## Future Capture Metrics

Future input timing and typo analytics should observe prompt behavior without changing stored metadata shape.

Possible event-level observations:

- field name
- prompt start time
- raw input
- canonical resolved value
- resolution method
- fuzzy score
- accepted or rejected result

The metadata JSON should continue storing canonical field values only unless a schema change is explicitly introduced.
