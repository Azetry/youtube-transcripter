## Context

`youtube-transcripter` now supports speaker-aware artifacts, but current v1 output depends on a pause-based heuristic. That means the repo's artifact shape and operator surface are ready, but the quality ceiling is limited by the attribution backend.

This change upgrades the backend architecture, not the product boundary. The repo should still generate transcript artifacts, not resolve named identities or produce article-level interpretation.

## Goals / Non-Goals

**Goals:**
- Improve speaker-turn accuracy first.
- Add one real post-hoc diarization backend behind a strategy boundary.
- Preserve the heuristic path as fallback/debug mode.
- Let operators explicitly select strategy in v2.
- Keep artifact compatibility and conservative uncertainty handling.
- Preserve long-video support with alignment/ambiguity controls.

**Non-Goals:**
- Named speaker identification.
- Host/Guest inference.
- Automatic multi-backend routing in v2.
- Provider lock-in as the primary architecture.
- Heavy redesign of acquisition/deployment/backup-service paths.

## Decisions

### 1. Strategy abstraction first
The current heuristic module should evolve into a strategy boundary rather than being replaced inline.

**Why:** This creates a clean seam for one real backend now and more backends later.

### 2. Post-hoc diarization first real backend
v2 should introduce one real post-hoc diarization backend before provider-native or hybrid routing expansion.

**Why:** This is the best balance of architectural control and product-value improvement.

### 3. Heuristic stays as fallback/debug mode
The pause-based heuristic remains available in v2.

**Why:** It provides graceful degradation, debugging value, and a baseline comparison mode.

### 4. Explicit operator strategy selection in v2
Operators should choose the strategy explicitly in CLI/API rather than relying on auto-selection.

**Why:** This keeps behavior understandable while backend quality is still being evaluated.

### 5. Conservative alignment and chunk-boundary handling
When long-video chunk reconciliation is ambiguous, the system should prefer downgraded confidence or `unknown` over false continuity.

**Why:** Product trust depends more on honest ambiguity than on aggressive but misleading continuity.

## Architecture direction

The next layer should be shaped roughly as:

1. transcription stage → timestamped transcript segments
2. diarization stage → speaker time ranges / turns
3. alignment stage → transcript-segment ↔ speaker-turn mapping
4. merge/reconciliation stage → chunk-boundary ambiguity handling

Likely implementation shape:
- evolve `src/transcript/speaker_attribution.py` into a strategy-oriented module or package
- keep orchestration ownership in `src/services/transcription_service.py`
- persist strategy/version metadata in artifacts and job metadata

## Risks / Trade-offs

- **Backend integration complexity** → Mitigate by integrating only one real backend in v2.
- **Alignment ambiguity** → Mitigate by formalizing uncertainty / unknown states.
- **Long-video chunk drift** → Mitigate by keeping conservative chunk-boundary downgrade rules.
- **Overbuilding routing policy** → Avoid by using explicit operator-selected strategy in v2.

## Migration plan

1. Introduce strategy abstraction while preserving heuristic mode.
2. Integrate one real post-hoc backend.
3. Add alignment logic from diarization turns to transcript segments.
4. Harden long-video ambiguity handling.
5. Expose explicit strategy selection in CLI/API.
6. Validate against golden videos first, then add benchmark scaffolding.

## Open Questions

- Which specific post-hoc backend should be the first implementation target?
- What is the minimal strategy-selection interface that keeps CLI/API understandable?
- What benchmark structure should follow golden-video acceptance?
