# AVFoundation Brio 100 Capture Notes

## Bottom Line

The Logitech Brio 100 can deliver real `1920x1080@30` on this macOS machine through native AVFoundation.

The failure mode was negotiation order, not camera capability:

1. Setting `AVCaptureDevice.activeFormat` before `AVCaptureSession.startRunning()` updated device state, but the delivered sample stream stayed around 24 fps.
2. Constraining `AVCaptureVideoDataOutput.videoSettings`, pinning `AVCaptureConnection` frame durations, starting the session, then applying `activeFormat` produced real 1080p30 samples.
3. Applying the same ordering to `AVCaptureMovieFileOutput` produced a real 1080p30 `.mov`.


## Binary Capabilities

`avcam-cli` currently supports more than the Privledger macOS recorder path needs.

Used by the planned macOS Privledger path:

- `record`
- camera selection by partial name, for example `--camera "Brio"`
- audio selection by partial name, for example `--audio "Brio"`
- explicit format selection with `--format-index 35`
- explicit frame-rate pinning with `--fps 30`
- ALAC audio with `--audio-codec alac`
- run-until-stop recording when `--seconds` is omitted
- timed recording when `--seconds` is provided
- graceful SIGINT/SIGTERM finalization
- `--finalize-timeout` for bounded MovieFileOutput finalization

Available but not planned for the first Privledger macOS wrapper:

- `list` to enumerate video and audio devices
- `formats` to enumerate AVFoundation camera formats
- `probe` to inspect raw `AVCaptureVideoDataOutput` delivery without writing a movie
- `--output-mode native|nv12` for probe diagnostics
- `--subtype` and `--width`/`--height` automatic format matching
- `--audio-codec aac` and `--audio-codec pcm`
- video-only recording, kept for debugging but not the default path
- exposure diagnostic/config flags used during camera investigation

The verified default macOS recording profile is Brio video format index `35`, `1920x1080 420v`, `30 fps`, Brio audio, ALAC, QuickTime `.mov` output.
## Verified Working Pattern

Use the Chromium-style ordering:

1. Create `AVCaptureSession`.
2. Add `AVCaptureDeviceInput`.
3. Add output.
4. Set output-side constraints:
   - width
   - height
   - pixel format
   - connection `videoMinFrameDuration`
   - connection `videoMaxFrameDuration`
5. Commit session configuration.
6. Call `session.startRunning()`.
7. Lock device.
8. Set:
   - `device.activeFormat`
   - `device.activeVideoMinFrameDuration`
   - `device.activeVideoMaxFrameDuration`
9. Unlock device.
10. Pin output connection frame durations again.
11. For recording, call `startRecording(...)` only after the session is running and active format is applied.


## Recording Flow

The recording path is session-based:

```text
parse CLI options
  -> request camera permission
  -> request microphone permission when --audio is present
  -> discover video devices with AVCaptureDevice.DiscoverySession
  -> select camera by partial name
  -> discover/select audio device when requested
  -> select AVCaptureDevice.Format
  -> create AVCaptureSession
  -> beginConfiguration()
  -> add AVCaptureDeviceInput for camera
  -> add AVCaptureDeviceInput for audio when requested
  -> create AVCaptureMovieFileOutput
  -> add movie output
  -> set output connection frame durations when connections are available
  -> set audio output codec settings when audio is present
  -> commitConfiguration()
  -> startRunning()
  -> lock camera for configuration
  -> set activeFormat and active video min/max frame durations
  -> unlock camera
  -> pin output connection frame durations again
  -> startRecording(to:recordingDelegate:)
  -> wait for didStartRecordingTo
  -> wait for --seconds, SIGINT, or SIGTERM
  -> call stopRecording()
  -> keep session running while waiting for didFinishRecordingTo
  -> stopRunning()
  -> print final path and ffprobe command
```

The key invariant is that `AVCaptureSession` stays alive until `AVCaptureMovieFileOutput` reports `didFinishRecordingTo`. Stopping the session before that callback can interfere with file finalization.
## Probe Result

Command:

```bash
cd /path/to/repo/tools/avcam-cli/.build/release

./avcam-cli probe --camera "Brio" --format-index 35 --fps 30 --seconds 10 --output-mode native
```

Important output:

```text
Selected format: [35] 1920x1080 420v @ 30.000-30.000 fps
First sample format: 1920x1080 420v (875704438) nv12/video-range
First sample duration: 1000/30000 (0.033s)
Probe samples: 299
Probe media span seconds: 9.958
Probe media fps: 29.926
Dropped frames: 0
```

This proves AVFoundation can deliver 1080p30 frames from the Brio when the session is configured in the right order.

## MovieFileOutput Result

The stable MVP recording path is `AVCaptureMovieFileOutput` with Brio video plus Brio audio encoded as ALAC.

Command:

```bash
cd /path/to/repo/tools/avcam-cli/.build/release

./avcam-cli record --camera "Brio" --audio "Brio" --audio-codec alac --format-index 35 --fps 30 --out ctrlc-test.mov --verbose
```

Stop with Ctrl+C. Important output:

```text
Recording stop requested by SIGINT; waiting up to 5s for MovieFileOutput to finish writing.
Recording finished in 0.071s after stopRecording().
Finished recording: /path/to/repo/tools/avcam-cli/.build/release/ctrlc-test.mov
```

Verification:

```bash
ffprobe -v error \
  -show_entries stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,pix_fmt,duration,sample_rate,channels \
  -of default=nw=1 ctrlc-test.mov
```

Observed result:

```text
index=0
codec_name=alac
codec_type=audio
sample_rate=48000
channels=1
duration=28.482500
index=1
codec_name=h264
codec_type=video
width=1920
height=1080
pix_fmt=yuv420p
r_frame_rate=30/1
avg_frame_rate=30/1
duration=28.500000
```

`mediainfo` also reported constant `30.000 FPS` for the video stream.

Video-only `AVCaptureMovieFileOutput` was not reliable enough as the default path; it could produce lower average frame rate even after capture was pinned. Adding audio with ALAC produced stable 1080p30 output and finalized cleanly.

## Format Exposure

macOS AVFoundation exposes the Brio 100 as YUV-like formats only:

```text
[35] 1920x1080 420v fps: 30.000-30.000 fps, 24.000-24.000 fps, 20-20 fps, 15.000-15.000 fps, 10-10 fps, 7.500-7.500 fps, 5-5 fps
[36] 1920x1080 yuvs fps: 5-5 fps
```

Linux `v4l2-ctl` exposes native `MJPG 1920x1080@30` for the same camera. On macOS, the public AVFoundation format list does not expose `MJPG`, `dmb1`, or `jpeg` for this device. The working macOS path records H.264 from AVFoundation-delivered `420v`/NV12 samples.

## FFmpeg AVFoundation Failure Mode

FFmpeg's `-f avfoundation` path still negotiates badly:

```bash
ffmpeg -hide_banner -f avfoundation -framerate 30 -video_size 1920x1080 -i "0:none" -t 10 -f null -
```

Observed behavior:

```text
Configuration of video device failed, falling back to default.
Selected pixel format (yuv420p) is not supported by the input device.
Supported pixel formats:
  uyvy422
  yuyv422
  nv12
  0rgb
  bgr0
Overriding selected pixel format to use uyvy422 instead.
Input #0, avfoundation, from '0:none':
  Stream #0:0: Video: rawvideo (UYVY / 0x59565955), uyvy422, 1920x1080, 1000k tbr, 1000k tbn
frame=50 fps=4.9 ... time=00:00:09.85
```

This is a different failure than the native CLI after the Chromium-style fix. FFmpeg falls back to a poor AVFoundation configuration and only gets about 5 fps at 1080p.

## Current Interpretation

The causal chain is:

```text
wrong AVFoundation negotiation order
  -> session starts with preset/default stream behavior
  -> activeFormat appears correct in device state
  -> delivered sample buffers still arrive at about 24 fps

Chromium-style ordering
  -> output constraints are known before session start
  -> connection frame durations are pinned
  -> activeFormat is applied after session is running
  -> delivered sample buffers arrive at about 30 fps
  -> MovieFileOutput records stable 30 fps when paired with Brio audio/ALAC
```

## Build

Build the release binary with:

```bash
cd /path/to/repo/tools/avcam-cli
./build.sh
```

The script writes:

```text
.build/release/avcam-cli
```
## Audio Recording

`record` can optionally add an audio input and request an audio codec on the `AVCaptureMovieFileOutput` audio connection.

Examples:

```bash
./avcam-cli record --camera "Brio" --audio "Brio" --audio-codec alac --format-index 35 --fps 30 --out brio-1080p30-alac.mov

./avcam-cli record --camera "Brio" --audio "Brio" --audio-codec alac --format-index 35 --fps 30 --seconds 10 --out brio-1080p30-alac.mov

./avcam-cli record --camera "Brio" --audio "Brio" --audio-codec pcm --format-index 35 --fps 30 --seconds 10 --out brio-1080p30-pcm.mov
```

Behavior:

- `--audio` selects an AVFoundation audio capture device by partial name.
- `--audio-codec` requires `--audio`.
- Supported requested audio codecs are `aac`, `alac`, and `pcm`.
- If `--audio` is passed without `--audio-codec`, the codec defaults to `aac`; the verified macOS target path uses `alac` explicitly.
- The embedded plist includes both camera and microphone usage descriptions.

Verification command:

```bash
ffprobe -v error -show_entries stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,pix_fmt,duration,sample_rate,channels -of default=nw=1 brio-1080p30-alac.mov
```
## Logging Behavior

`probe` remains the full diagnostic command.

`record` is quieter by default and prints:

- selected camera
- selected format
- pinned frame duration
- output path
- final recording path
- ffprobe-style inspection command

Pass `--verbose` to `record` to print the Chromium-style ordering note, active format after session start, and movie output connection frame-duration details.

`record` can run until Ctrl+C/SIGTERM, or stop automatically when `--seconds` is provided. Every stop path requests `AVCaptureMovieFileOutput.stopRecording()`, keeps the `AVCaptureSession` running while it waits for `didFinishRecordingTo`, and pumps the main run loop so AVFoundation delegate delivery is not starved by a blocking CLI sleep. The session stops only after the finish callback arrives, or after `--finalize-timeout` seconds with an explicit timeout error.


## Privledger Boundary

`avcam-cli` owns AVFoundation correctness:

- device selection
- format selection
- session start order
- signal/duration stop handling
- `stopRecording()`
- waiting for `didFinishRecordingTo`
- final recorder exit code

`record-macos.sh` should own Privledger artifact handling:

- read `TIMESTAMP` and macOS recorder env
- create `vlog/` and `logs/`
- write to a temp media file
- run `avcam-cli`
- forward signals to `avcam-cli`
- validate the produced media with `ffprobe`
- atomically move temp output to the final artifact
- mark degraded output as `.bad`

`privledger.py` should remain the supervisor: it owns timestamp creation, recorder process supervision, filesystem-based artifact classification, metadata writing, and final pipeline exit behavior. Later it can choose `record.sh` or `record-macos.sh` based on OS.
