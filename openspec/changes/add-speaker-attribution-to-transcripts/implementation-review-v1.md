# Implementation Review Note — Speaker Attribution v1

**Date:** 2026-03-28
**Spec:** add-speaker-attribution-to-transcripts
**Status:** Pre-implementation review

---

## 1. Approach Summary

Add optional speaker attribution to the transcript pipeline as an opt-in feature.
Speaker labels are generic (`Speaker A`, `Speaker B`, etc.) with explicit confidence
and attribution mode fields. The canonical output format is JSON. All existing
non-attribution behavior is preserved unchanged.

## 2. V1 Attribution Strategy Decision

**Chosen path: Pause-based heuristic diarization (post-hoc, no new dependencies)**

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| Whisper native diarization | Zero extra work | Whisper API does **not** provide speaker labels | Not available |
| pyannote.audio / external diarization | High quality | Heavy GPU dependency, new pip install, licensing | Deferred to v2 |
| Pause-based heuristic | Zero new deps, honest about uncertainty, demonstrates full pipeline | Low accuracy | **Chosen for v1** |

**Rationale:** The v1 goal is to build the full schema/pipeline/merge infrastructure
and prove it end-to-end. A pause-based heuristic assigns speaker turns by detecting
gaps > 2 seconds between segments. All attributions are marked `attribution_mode: "predicted"`
with moderate confidence (0.3–0.5). This is explicitly a "low-confidence guess" — exactly
what the spec requires to be representable. A real diarization engine can be swapped in
later without schema or pipeline changes.

## 3. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Heuristic speaker labels are inaccurate | Low (expected, explicitly marked) | `confidence` field + `attribution_mode: "predicted"` |
| Schema migration breaks existing DB rows | Medium | Additive-only migration (new columns, nullable) |
| Merge falsely continues speaker identity across chunks | Medium | Reset speaker state at chunk boundaries, mark cross-chunk as `"unknown"` |
| Feature flag not properly threaded through all paths | Medium | Tested via backward-compat tests (attribution off = identical output) |
| API response size increase | Low | Speaker segments only included when requested |

## 4. Backward Compatibility Guarantee

When `speaker_attribution=False` (the default):
- `TranscriptArtifacts` fields are identical to current behavior
- `Segment` objects carry no speaker metadata
- API response shape is unchanged
- Storage schema is additive (new nullable columns only)
- Input signature includes `speaker_attribution` flag, so cached results are correctly separated

## 5. Files to Modify

| File | Change |
|------|--------|
| `src/transcript/models.py` | Add `SpeakerInfo` dataclass, extend `Segment` with optional speaker field |
| `src/models/transcript.py` | Add speaker metadata fields to `TranscriptArtifacts` |
| `src/models/job.py` | Add `speaker_attribution: bool` to `Job` |
| `src/transcript/merger.py` | Preserve speaker labels through global timeline mapping + dedup |
| `src/services/transcription_service.py` | Wire attribution flag, call attribution pipeline |
| `src/services/job_service.py` | Thread `speaker_attribution` through create_job |
| `src/storage/schema.py` | Schema v4: add speaker columns to jobs + job_results |
| `src/storage/sqlite_store.py` | Persist/retrieve speaker_attribution flag |
| `src/storage/signatures.py` | Include speaker_attribution in signature |
| `api/main.py` | Add `speaker_attribution` to request/response models |
| `main.py` | Add `--speakers` CLI flag |
| **New:** `src/transcript/speaker_attribution.py` | Pause-based heuristic attribution engine |
| **New:** `tests/test_speaker_attribution.py` | Tests for attribution + backward compat |

## 6. What This Does NOT Do

- No named speaker inference (Host/Guest)
- No external diarization library
- No article generation
- No redesign of acquisition, correction, or diff pipeline
- No changes to backup/delegation protocol (speaker_attribution flag is local-only in v1)
