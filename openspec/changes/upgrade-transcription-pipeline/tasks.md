## 1. Shared orchestration and models

- [ ] 1.1 Create canonical job and transcript models under `src/models/`.
- [ ] 1.2 Add `src/services/transcription_service.py` for shared end-to-end orchestration.
- [ ] 1.3 Add `src/services/job_service.py` for job lifecycle, status, and reuse decisions.
- [ ] 1.4 Refactor `main.py` to call the shared service layer.
- [ ] 1.5 Refactor `api/main.py` to call the shared service layer.

## 2. SQLite persistence

- [ ] 2.1 Add SQLite schema/bootstrap logic under `src/storage/schema.py`.
- [ ] 2.2 Add `src/storage/sqlite_store.py` for job, metadata, chunk, and artifact persistence.
- [ ] 2.3 Persist job lifecycle states, progress fields, and explicit error metadata.
- [ ] 2.4 Implement exact-input signature generation and reuse lookup.

## 3. Long-video processing

- [ ] 3.1 Add deterministic audio chunking with 10-minute target chunks and 15-second overlap.
- [ ] 3.2 Persist chunk metadata including index, time bounds, and artifact paths.
- [ ] 3.3 Extend transcription flow to support per-chunk timestamped outputs.
- [ ] 3.4 Extend correction flow to support per-chunk correction for long videos.

## 4. Merge and artifact generation

- [ ] 4.1 Add a merger that maps chunk-relative timestamps onto a global timeline.
- [ ] 4.2 Implement overlap deduplication using timestamps first and normalized text similarity second.
- [ ] 4.3 Generate merged raw transcript, merged corrected transcript, and merged segment artifacts.
- [ ] 4.4 Run a lightweight final consistency pass on merged corrected output.
- [ ] 4.5 Persist diff summaries and artifact paths in the stable result schema.

## 5. API and CLI behavior

- [ ] 5.1 Update `POST /api/transcribe` to create persistence-backed jobs and report reuse decisions.
- [ ] 5.2 Update `GET /api/task/{id}` to return persistence-backed job status and results.
- [ ] 5.3 Add a recent-jobs API endpoint for persisted history.
- [ ] 5.4 Preserve the simple CLI invocation path while surfacing job identifiers and artifact locations.

## 6. Validation

- [ ] 6.1 Add tests for signature generation, chunk planning, merge/dedupe behavior, and SQLite persistence.
- [ ] 6.2 Add integration coverage for short-video flow, long-video flow, and restart-safe job lookup.
- [ ] 6.3 Verify Docker Compose still supports local development after the pipeline upgrade.
- [ ] 6.4 Run `openspec validate --strict` successfully for this change.
