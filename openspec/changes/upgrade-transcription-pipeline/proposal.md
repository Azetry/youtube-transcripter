## Why

The current repo proves the core YouTube → audio → Whisper → GPT correction flow, but it is still structured like a single-user MVP. Duplicated orchestration logic, in-memory job tracking, and lack of long-video handling will make future upgrades fragile and expensive.

## What Changes

- Introduce a shared service-layer transcription pipeline used by both CLI and API.
- Add persistent job and artifact storage backed by SQLite so completed jobs survive process restarts.
- Add long-video processing using deterministic audio chunking with overlap, chunk-level transcription/correction, and merged transcript outputs.
- Add stable transcript/job schemas covering input parameters, video metadata, chunks, segments, artifacts, lifecycle state, and error states.
- Extend the API to support persisted jobs, history lookup, and exact-input reuse behavior.
- Keep lightweight local usage intact through the existing CLI and Docker Compose deployment path.

## Capabilities

### New Capabilities
- `job-orchestration`: Shared transcript job lifecycle and orchestration across CLI and API.
- `job-persistence`: Persistent storage of jobs, statuses, and artifacts across restarts.
- `long-video-processing`: Chunked processing for videos exceeding single-file transcription limits.
- `transcript-artifacts`: Stable transcript outputs including raw/corrected text, diff summaries, and timestamped segments.

### Modified Capabilities
- None.

## Impact

- Affected code: `main.py`, `api/main.py`, `src/whisper_transcriber.py`, `src/text_corrector.py`, `src/diff_viewer.py`, `src/youtube_extractor.py`
- New modules: service layer, SQLite storage layer, chunker, merger, schema/models utilities
- APIs: `/api/transcribe`, `/api/task/{id}` behavior becomes persistence-backed; new task history endpoint expected
- Dependencies/systems: SQLite and ffmpeg become explicit parts of the upgraded workflow
