import json
from pathlib import Path
from metadata.writer import write_metadata_atomic

# Load schema
schema = json.loads(Path("tests/schema/metadata.v1.schema.json").read_text())

# Call writer
written = write_metadata_atomic(
    output_path=Path("vlog/2026-02-27-0727.json"),
    entry_id="2026-02-27-0727",
    timestamp_utc="2026-02-27T07:27:00Z",
    media_file="2026-02-27-0727.mkv",
    metadata_quality="basic",
    schema_version=1,
    pipeline_version="0.1.0",
    optional_fields=None,
    schema=schema,
)

print(f"Written: {written}")
print(written.read_text())
