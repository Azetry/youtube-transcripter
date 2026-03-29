## Context

The upgraded pipeline already produces persisted transcript artifacts and supports long-video chunking/merge, but all segments are effectively speaker-agnostic. For interview and podcast content, downstream workflows need segment-level structure that answers not only "what was said" and "when", but also "who likely said it" and "how certain are we".

This change should keep the repo's role narrow: generate transcript artifacts with optional speaker attribution. It should not attempt full speaker identity resolution, role inference, or downstream content generation.

## Goals / Non-Goals

**Goals:**
- Add optional speaker-attribution mode to transcript jobs.
- Make structured JSON the canonical transcript artifact for speaker-aware output.
- Support generic speaker labels (`Speaker A/B/C`) plus explicit uncertainty/confidence.
- Preserve compatibility for single-speaker and speaker-agnostic outputs.
- Preserve speaker-labeled segments through long-video chunking/merge well enough for interview/podcast use cases.

**Non-Goals:**
- Perfect diarization.
- Named speaker or role inference (for example `Host` / `Guest`) in v1.
- Robust support for roundtables or heavily overlapping speech.
- Article generation or downstream narrative transformation.
- Multimodal identity resolution.

## Decisions

### 1. Speaker attribution is opt-in
Jobs will explicitly request speaker attribution rather than enabling it for all transcripts by default.

**Why:** Existing workflows should remain stable, and speaker attribution quality is situational.

### 2. JSON artifact is the canonical source
Speaker-aware output will be modeled first in structured JSON; plain text and subtitle-like renderings derive from that artifact.

**Why:** Downstream agents need a stable machine-readable representation of timing, text, and speaker metadata.

### 3. Conservative generic labels first
v1 uses generic labels such as `Speaker A/B/C` rather than trying to infer names or roles.

**Why:** This preserves product value while avoiding brittle overreach.

### 4. Uncertainty must be explicit
Speaker assignment may be tentative, but tentative assignments must be represented as low-confidence or predicted rather than implied as certain.

**Why:** Overconfident wrong labels are more damaging downstream than partial but honest attribution.

### 5. Long-video merge preserves speaker-labeled segments conservatively
Chunk merge will preserve segment-level speaker metadata when available. If chunk-level mapping drifts or cannot be reconciled confidently, the merged artifact should prefer explicit uncertainty over forced continuity.

**Why:** Long-video support matters, but speaker continuity across chunks is an ambiguity source that should not be hidden.

## Data Model Direction

A canonical speaker-aware segment should support fields equivalent to:
- `start`
- `end`
- `text`
- `speaker.label`
- `speaker.confidence`
- `speaker.attribution_mode` (`confident`, `predicted`, `unknown`)
- optional provenance such as `segment_id`, `chunk_id`, `source`

Job/result metadata should also record whether speaker attribution was requested and which attribution strategy/version produced the output.

## Risks / Trade-offs

- **Speaker drift across chunks** → Mitigate by preserving provenance and allowing uncertain/unknown speaker labels instead of forcing continuity.
- **False confidence in attribution** → Mitigate by requiring confidence/attribution mode in canonical artifacts.
- **Schema growth complicates backward compatibility** → Mitigate by keeping speaker metadata optional and additive.
- **Temptation to infer roles/names in v1** → Reject to preserve repo boundary and reduce misleading outputs.

## Migration Plan

1. Extend job/request models to represent optional speaker-attribution mode.
2. Extend transcript artifact schema/models with optional speaker metadata.
3. Integrate a first speaker-attribution path into transcript generation.
4. Update long-video merge to preserve speaker-labeled segments and uncertainty.
5. Keep plain text/subtitle renderers compatibility-backed by the structured artifact.
6. Validate short-video, long-video, and single-speaker regression cases.

## Open Questions

- What exact CLI/API flag or request field should enable speaker attribution?
- What is the minimal canonical JSON schema guaranteed to downstream consumers?
- What merge heuristic is acceptable when chunk-level speaker identities cannot be reconciled confidently?
