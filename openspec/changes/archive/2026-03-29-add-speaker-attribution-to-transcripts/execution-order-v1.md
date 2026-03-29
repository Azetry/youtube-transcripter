# Task Execution Order — Speaker Attribution v1

**Date:** 2026-03-28

---

## Phase 1: Schema & Models (no pipeline changes yet)

1. **Add `SpeakerInfo` dataclass and extend `Segment`** (`src/transcript/models.py`)
   - New frozen dataclass `SpeakerInfo(label, confidence, attribution_mode)`
   - Extend `Segment` with `speaker: Optional[SpeakerInfo] = None`
   - Segment remains frozen; speaker is set at construction time

2. **Extend `TranscriptArtifacts`** (`src/models/transcript.py`)
   - Add `speaker_attribution_enabled: bool = False`
   - Add `speaker_strategy: str = ""`
   - Add `speaker_count: int = 0`
   - Add `speaker_segments: Optional[list] = None` (serializable segment dicts)

3. **Extend `Job` model** (`src/models/job.py`)
   - Add `speaker_attribution: bool = False`

## Phase 2: Request Surface & Persistence

4. **Update input signature** (`src/storage/signatures.py`)
   - Include `speaker_attribution` in signature hash

5. **Update storage schema to v4** (`src/storage/schema.py`)
   - Add `speaker_attribution INTEGER NOT NULL DEFAULT 0` to `jobs`
   - Add `speaker_attribution_enabled INTEGER`, `speaker_strategy TEXT`,
     `speaker_count INTEGER`, `speaker_segments_json TEXT` to `job_results`

6. **Update SQLiteStore** (`src/storage/sqlite_store.py`)
   - Persist `speaker_attribution` flag in job insert
   - Persist speaker fields in result insert
   - Read speaker_attribution flag in `_row_to_job()`

7. **Update JobService** (`src/services/job_service.py`)
   - Thread `speaker_attribution` through `create_job()`

8. **Update API request/response** (`api/main.py`)
   - Add `speaker_attribution: bool = False` to `TranscribeRequest`
   - Add optional speaker fields to `TranscribeResponse`
   - Thread flag through `process_transcription()`

9. **Update CLI** (`main.py`)
   - Add `--speakers` flag
   - Thread through `process_video()` → `service.run()`

## Phase 3: Attribution Pipeline

10. **Create speaker attribution module** (`src/transcript/speaker_attribution.py`)
    - `attribute_speakers(segments, strategy="pause_heuristic_v1") -> list[Segment]`
    - Pause-based heuristic: gap > 2s = speaker change
    - Alternating Speaker A/B labels
    - All assignments: `attribution_mode="predicted"`, `confidence=0.3–0.5`

11. **Wire into TranscriptionService** (`src/services/transcription_service.py`)
    - Accept `speaker_attribution` parameter in `run()`
    - Call `attribute_speakers()` after Whisper transcription
    - For short videos: attribute after `transcribe_with_timestamps()`
    - For long videos: attribute per-chunk before merge

## Phase 4: Merge Behavior

12. **Extend merger for speaker-aware segments** (`src/transcript/merger.py`)
    - `map_to_global_timeline()`: preserve `speaker` field on mapped segments
    - `dedupe_overlap_segments()`: when deduping, keep prev-chunk's speaker label
    - At chunk boundaries: reset speaker labels to `attribution_mode="unknown"`
      for the first segment of each new chunk (uncertainty > false continuity)

## Phase 5: Validation

13. **Write tests** (`tests/test_speaker_attribution.py`)
    - Backward compat: attribution off produces identical output
    - Short video: speaker segments present when enabled
    - Long video: merge preserves speaker labels, chunk boundaries marked unknown
    - Low-confidence assignments distinguishable in output
    - Schema validation of speaker segment structure

14. **Run full test suite**
    - Existing tests must pass unchanged
    - New tests must pass
