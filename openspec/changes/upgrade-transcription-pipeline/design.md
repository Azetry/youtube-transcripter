## Context

`youtube-transcripter` currently has a clean MVP pipeline, but orchestration is duplicated between CLI and FastAPI entrypoints. The API stores task state only in memory, so completed jobs disappear on restart. Long videos are constrained by the Whisper single-file size limit, and current transcript outputs are not modeled as a stable, reusable artifact set for downstream workflows.

The upgrade must preserve current lightweight local operation while turning the repo into a more durable transcript-processing foundation.

## Goals / Non-Goals

**Goals:**
- Unify CLI and API around one service-layer transcription pipeline.
- Persist jobs, statuses, and output artifacts in SQLite.
- Support long videos via deterministic time-based chunking with overlap.
- Merge chunk outputs into stable transcript artifacts with timestamps and diff summaries.
- Preserve local CLI and Docker Compose workflows.

**Non-Goals:**
- Multi-tenant auth, billing, or permissions.
- Production-grade distributed queue infrastructure.
- Perfect speaker diarization.
- Non-YouTube media ingestion in this change.
- Real-time websocket progress streaming.

## Decisions

### 1. Shared service layer
A new service layer will own job creation, orchestration, lifecycle transitions, artifact persistence, and cleanup. CLI and API will become thin entrypoints.

**Why:** This removes duplicated flow logic and gives future changes one place to evolve.

**Alternative considered:** Keep separate CLI/API flows with copied logic. Rejected because chunking, persistence, and retries would drift quickly.

### 2. SQLite as first persistence backend
Jobs, request inputs, video metadata, chunk metadata, and artifact paths/summaries will be persisted in SQLite.

**Why:** SQLite is the fastest path to restart-safe persistence without introducing unnecessary infra for a single-node repo.

**Alternative considered:** Postgres first. Rejected for now because it adds operational complexity before the product boundary justifies it.

### 3. Deterministic time-based chunking with overlap
Long videos will use time-based chunking with an initial default of 10-minute chunks and 15-second overlap.

**Why:** This is simpler and more debuggable than silence-aware or VAD-based splitting while still reducing boundary sentence truncation.

**Alternative considered:** Silence-aware chunking. Rejected for first iteration because it adds implementation and debugging complexity too early.

### 4. Chunk-first correction plus final consistency pass
Each chunk will be transcribed and corrected individually; merged output will then receive a lightweight consistency pass.

**Why:** This balances long-form stability with final readability without forcing the whole transcript through one very large correction step.

**Alternative considered:** single global correction only. Rejected because cost and instability increase on longer transcripts.

### 5. Merge by timestamps first, dedupe by overlap text second
Chunk-relative segment timestamps will be mapped onto a global timeline. Overlap deduplication will use timestamp overlap as the primary signal and normalized text similarity as a secondary safeguard.

**Why:** Timestamp-led merging preserves traceability and is more robust than text-only merging.

### 6. Exact-signature reuse policy
Completed jobs may be reused only when normalized inputs and strategy versions match exactly.

**Why:** This preserves deterministic reuse while preventing stale results after chunking/correction logic changes.

## Risks / Trade-offs

- **Chunk boundary duplication or truncation** → Mitigate with 15-second overlap plus timestamp-aware merge/dedupe.
- **SQLite schema drift during iteration** → Mitigate by isolating DB access in a storage module and versioning strategy inputs.
- **Chunk-first correction may reduce full-document consistency** → Mitigate with a final lightweight consistency pass.
- **More artifacts and metadata increase implementation surface** → Mitigate by introducing explicit models and a single artifact persistence boundary.
- **Polling-based API progress is less elegant than streaming** → Accept for now; streaming can be a later enhancement.

## Migration Plan

1. Add service-layer and model modules without removing current behavior.
2. Introduce SQLite initialization and persistence-backed job lifecycle.
3. Refactor CLI and API to call shared services.
4. Add chunking, chunk transcription/correction, merge, and artifact persistence.
5. Extend API responses for persisted jobs/history while preserving compatibility for existing task lookup.
6. Update frontend to reflect persisted job status and history.
7. Validate with short-video, long-video, and restart-survival checks.

Rollback strategy:
- The change can be rolled back by reverting the new OpenSpec change and removing SQLite-backed paths if required.
- Existing CLI single-run behavior remains conceptually preserved through the service layer, reducing rollback risk.

## Open Questions

- Should merged segments be stored as JSON blobs first, or normalized into a separate `chunk_segments` table immediately?
- Should per-chunk retry be included in the first implementation or deferred until the initial long-video path is stable?
- Should API compatibility preserve `/api/task/{id}` naming long-term, or introduce `/api/jobs/{id}` once the persistence-backed model is stable?
