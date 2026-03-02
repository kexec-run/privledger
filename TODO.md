# privledger TODO

## Capture Pipeline

[x] Finalize and freeze ffmpeg capture command  
[x] Add `-fflags +genpts` to video input  
[x] Verify VAAPI device presence at runtime  
[x] Verify Pulse audio source exists at runtime  
[x] Run 15–20 minute capture validation test  
[x] Inspect output with ffprobe for A/V sync and duration  
[x] Confirm pixel format and codec correctness  
[x] Wrap ffmpeg in atomic-safe record.sh  
[x] Verify output duration > 0 via ffprobe (using format.duration, advisory)

## record.sh Hardening

[x] Write to temp file first  
[x] Check ffmpeg exit code  
[x] Verify output file is non-zero  
[x] Rename atomically on success  
[x] Fail loudly on any capture error  
[x] Ensure vlog directory auto-creation
[x] Add STOP_SENT idempotence guard in on_int
[x] Python-owned TIMESTAMP passed to record.sh

## Metadata Layer

[x] Implement schema validation helper in Python
[x] Load versions from config/env 
[x] Assert env variables exist at startup
[x] Generate minimal metadata object
[x] Validate metadata against schema
[x] Fail write on schema validation error
[x] Atomic write for metadata file
[x] Enforce tags invariant post-merge
[x] Enforce optional_fields type check
[x] parent.mkdir guard in writer
[x] Use os.replace for atomic rename
[x] Wire writer into privledger.py post-capture
[x] 20–30 minute soak test (metadata enabled)

## Metadata Hardening

[x] Add timestamp_local to metadata output
[x] Add video_device annotation
[x] Three-way filesystem check in supervisor
[ ] Implement result file handoff in record.sh
[ ] Parse result file in privledger.py
[ ] Add mtime freshness guard


## Enrich Workflow

[x] Implement basic enrich CLI
[ ] Load controlled vocabulary from config/tags.txt
[ ] Single-select focus_domain
[ ] Multi-select tags (exclude focus)
[ ] Enforce focus not present in tags
[ ] Normalize inputs before validation
[ ] Update metadata_quality on success

## Terminal Compatibility

[x] Add stty icrnl workaround in shell init for Enter key normalization

## Testing Foundation

[ ] Create fixtures/basic.json  
[ ] Create fixtures/enriched.json  
[ ] Create expected/basic.expected.json  
[ ] Create expected/enriched.expected.json  
[ ] Implement canonical JSON dump for comparison  
[ ] Write first regression test  

## Observability

[ ] Media sanity check using ffprobe  
[ ] Log capture start and end times  
[ ] Add basic failure logging  

## Deferred (Do Not Build Yet)

[ ] SQLite index  
[ ] HEVC secondary transcode  
[ ] S3/archive upload  
[ ] fzf integration  
[ ] Advanced audio analytics  
[ ] Tag enum enforcement in schema  
[ ] Concurrency locking  
