# Operations

This doc covers local setup, commands, recording, enrichment, and verification.

## Requirements

Python dependencies are listed in `requirements.txt`.

Runtime configuration lives in `config/env`.
Tag vocabulary lives in `config/tags.txt`.

## Commands

Record a session:

```bash
python3 scripts/privledger.py
```

`scripts/privledger.py` detects macOS with `platform.system() == "Darwin"` and uses `scripts/record-mac.sh`. Other platforms use `scripts/record-linux.sh`.

Record and immediately open metadata enrichment after a clean non-bad artifact:

```bash
python3 scripts/privledger.py --enrich
```

Enrich an existing session:

```bash
python3 scripts/enrich.py 2026-02-27-0727.json
```

The argument may be a timestamp, JSON filename, media filename, or path that resolves to a timestamp.

Run focused behavior tests:

```bash
PYTHONPATH=. pytest tests/test_writer_invariants.py tests/test_enrich_behavior.py -q
```

Run lint:

```bash
uv run ruff check .
```

Run type checking:

```bash
uv run basedpyright
```

## Recording Output

Recording writes into `vlog/`.

Possible media outcomes:

- `TS.mkv`
- `TS.mkv.bad.mkv`
- `TS.mov`
- `TS.mov.bad.mov`
- no media artifact

Metadata is written as:

```text
vlog/TS.json
```

Logs are written under `logs/` and are disposable. `vlog/` is durable state.

## macOS Testing Constraint

Webcam-backed recording is not available in this environment.

Recording behavior should be tested with mocked artifacts and mocked recorder outcomes. The tests should verify behavior from filesystem state rather than relying on real camera access.

## Verification Baseline

For Python changes, run:

```bash
uv run basedpyright
uv run ruff check .
```

Then run the narrowest relevant tests.

Known current status:

- focused writer/enrichment tests pass
- broader supervisor behavior includes a documented deviation for `.bad.mkv` with recorder exit `0`
- `basedpyright` currently fails globally due existing import/type backlog
