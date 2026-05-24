# Test Matrix

Tests should encode documented behavior as pass/fail cases. Failure cases must assert the expected error and that durable state is not written or is unchanged.

## Recording / Supervisor

Source: `docs/arch.md` failure matrix and `docs/operations.md` macOS mock constraint.

| Invariant | Success case | Failure case | Expected assertion |
|---|---|---|---|
| Successful capture writes basic metadata | Recorder exits `0`; only `TS.mkv` exists | Recorder exits `0`; no artifact exists | Success writes `TS.json` with `metadata_quality=basic`; no-artifact case writes no metadata and exits failure |
| Degraded capture writes bad metadata | Recorder exits non-zero; only `TS.mkv.bad.mkv` exists | Recorder exits non-zero; no artifact exists | Bad artifact writes `metadata_quality=bad` and exits non-zero; no-artifact case writes no metadata |
| Filesystem is authoritative | Recorder exit code conflicts with artifact state | Exit code alone implies success/failure without matching file | Classification follows files, not exit code |
| Good and bad artifacts are mutually exclusive | Exactly one media artifact exists | Both `TS.mkv` and `TS.mkv.bad.mkv` exist | Both-artifacts case writes no metadata and exits `2` |
| Metadata failure does not delete media | Media artifact exists; metadata write succeeds | Media artifact exists; metadata validation/write fails | Media remains; final `TS.json` is absent or unchanged |

## Metadata / Schema

Source: `docs/metadata.md` and `tests/schema/metadata.v1.schema.json`.

| Invariant | Success case | Failure case | Expected assertion |
|---|---|---|---|
| Required fields exist | `id`, `timestamp_utc`, `schema_version`, `pipeline_version`, `metadata_quality`, `media_file` present | Any required field missing | Validation fails; no final file written |
| Unknown fields are rejected | Only schema-defined fields present | `unknown_field` present | Validation fails; no final file written |
| Metadata quality is known | `basic`, `full`, `corrected`, or `bad` | Any other value | Validation fails; no final file written |
| Numeric 1-5 fields are bounded | `mood`, `energy`, `stress`, `sleepiness` are `null` or `1..5` | Value below `1` or above `5` | Validation fails; no final file written |
| Non-negative numeric fields are bounded | `sleep_hours`, `caffeine_mg`, `body_weight` are `null` or `>=0` | Negative value | Validation fails; no final file written |
| `transcript_file` is nullable or non-empty | `null` or non-empty string | Empty string | Validation fails; no final file written |

## Tags / Focus Domain

Source: `docs/metadata.md`, `docs/tags.md`, and shared predicates in `metadata/tags.py`.

| Invariant | Success case | Failure case | Expected assertion |
|---|---|---|---|
| Tags are a list | `tags=[]` or list of strings | `tags` is a scalar/object | Invariant check fails; no final file written |
| Tags contain strings | `["programming"]` | `[1]`, `[null]`, or object item | Invariant check fails; no final file written |
| Tags are lowercase | `["smoking"]` | `["Smoking"]` or `["SMOKING"]` | Invariant check fails; no final file written |
| Tags are unique | `["programming", "fatigue"]` | duplicate tag values | Validation fails; no final file written |
| Tags are capped at five | 0-5 tags | 6+ tags | Validation fails; no final file written |
| Focus domain can be empty | `focus_domain=null` | None; empty is explicitly valid | Valid metadata writes |
| Focus domain is a special primary tag | `focus_domain` is null or one tag from `config/tags.txt` | `focus_domain` is not in configured tag vocabulary | Invariant check fails; no final file written |
| Focus domain is stored separately from regular tags | `focus_domain="sleep"` with `tags=["chores"]` | `focus_domain="sleep"` with `tags=["sleep"]` | Invariant check fails; enrichment rejects the duplicate and re-prompts |
| Shared tag predicates are the source of truth | `metadata/check.py` and `scripts/enrich.py` call `metadata/tags.py` helpers | Same exact rule is reimplemented separately in each caller | Tests should fail or review should reject drift-prone duplicate logic |

## Custom Metadata

Source: `docs/metadata.md` and `metadata/check.py` custom schema invariants.

| Invariant | Success case | Failure case | Expected assertion |
|---|---|---|---|
| Disabled custom schema omits `custom` | Custom schema disabled and no `custom` key | `custom` key present while disabled | Custom invariant fails |
| Enabled custom schema has `custom` state | Custom schema enabled and `custom=null` before enrichment | Custom schema enabled and `custom` key absent | Custom invariant fails |
| Enriched custom metadata has envelope | `custom={"schema_hash": "...", "data": {...}}` | Missing `schema_hash` or `data` | Custom invariant fails |
| Current custom schema keys match exactly | `custom.data` keys equal active schema fields | Missing or extra key when hash matches | Custom invariant fails |
| Custom schema hash is valid | 12-character lowercase hex hash | Invalid hash format | Custom invariant fails |
| Custom values match declared types | Values are `null` or declared primitive type | Wrong primitive type or non-primitive object | Custom invariant fails |
| Old custom schema can remain readable | Hash mismatch with primitive old data | Hash mismatch with non-primitive old data | Primitive old data passes; non-primitive old data fails |

## Enrichment Behavior

Source: `docs/enrichment.md`, `scripts/enrich.py`, and tag input resolution behavior.

| Invariant | Success case | Failure case | Expected assertion |
|---|---|---|---|
| Immutable fields are preserved | User updates mutable fields only | User input tries to change immutable fields | Immutable fields remain original |
| Empty input keeps current value | Prompt receives empty input | Empty input clears required/immutable value | Current value is preserved |
| Numeric input is normalized before write | Numeric strings parse to valid numbers | Invalid or out-of-range numeric input | Invalid input is rejected or re-prompted; no bad write |
| Fuzzy tag input resolves before validation | `chroes` resolves to canonical `chores` | Raw typo is written into JSON | Only canonical tag value reaches write-time validation |
| Ambiguous fuzzy tag input asks the user | Multiple plausible matches are shown as choices | Ambiguous raw input silently picks one option | User selects one canonical value before write |
| Tag selection uses vocabulary when enabled | Selected tags exist in `config/tags.txt` | Unknown selected tag | Unknown tag rejected; no bad write |
| Tag selection preserves core invariants | Selected tags are lowercase, unique, <=5 | Adapter returns duplicates, uppercase, or >5 | Shared invariant layer rejects bad output |
| Focus domain is selected before regular tags | Focus domain selected from configured vocabulary, then regular tags exclude it | Regular tags duplicate the selected focus domain | Duplicate is rejected and re-prompted before write |
| Cancelled enrichment writes nothing | User completes all prompts | User cancels midway | Existing metadata remains unchanged |
