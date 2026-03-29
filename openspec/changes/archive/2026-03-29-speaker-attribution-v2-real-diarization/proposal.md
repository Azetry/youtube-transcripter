## Why

`speaker attribution v1` already proved the transcript-artifact plumbing, but its pause-based heuristic backend is only a placeholder. The next meaningful product improvement is better speaker-turn quality, not more surface cleanup.

We need a focused follow-up that introduces a real diarization path without destabilizing the repo: add a strategy abstraction, keep heuristic mode as fallback/debug behavior, and implement one real post-hoc diarization backend first.

## What Changes

- Introduce a speaker-attribution strategy abstraction.
- Keep the existing heuristic path available as fallback/debug mode.
- Add one real post-hoc diarization backend as the first non-heuristic strategy.
- Let operators explicitly choose the speaker-attribution strategy in v2.
- Harden alignment / uncertainty handling for long-video chunk boundaries.

## Capabilities

### New Capabilities
- `speaker-attribution-strategies`: Multiple attribution strategies with explicit operator selection.
- `posthoc-diarization`: A real post-hoc diarization backend for speaker-turn assignment.

### Modified Capabilities
- `transcript-artifacts`: Speaker-aware transcript artifacts now carry strategy metadata for heuristic vs real diarization output.
- `long-video-processing`: Long-video merge must preserve conservative uncertainty handling with real diarization-backed speaker turns.
- `job-orchestration`: Jobs may explicitly request a speaker-attribution strategy.

## Impact

- Affected code: speaker-attribution modules, transcription orchestration, artifact models, storage/signatures, CLI/API request surface, long-video alignment/merge logic.
- Main design concern: improve turn accuracy without overstating confidence or overfitting to one provider.
- Out of scope: named speaker identity, Host/Guest inference, article generation, and broad multi-backend auto-routing.
