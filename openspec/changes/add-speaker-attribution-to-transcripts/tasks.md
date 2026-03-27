## 1. Request surface and orchestration

- [ ] 1.1 Define the job/request model for optional speaker attribution.
- [ ] 1.2 Surface speaker-attribution settings through the shared orchestration/service layer.
- [ ] 1.3 Persist speaker-attribution request metadata and strategy version with each job.

## 2. Canonical transcript artifact schema

- [ ] 2.1 Extend transcript artifact models with optional speaker metadata on segments.
- [ ] 2.2 Define canonical JSON output fields for `speaker.label`, `speaker.confidence`, and `speaker.attribution_mode`.
- [ ] 2.3 Ensure plain text / subtitle-like outputs derive from the canonical structured artifact without breaking current usage.

## 3. Speaker attribution pipeline

- [ ] 3.1 Compare provider-native speaker support vs post-hoc diarization and choose the lowest-risk viable v1 path.
- [ ] 3.2 Implement a conservative generic-label attribution flow (`Speaker A/B/C`).
- [ ] 3.3 Ensure low-confidence guesses are explicitly marked rather than silently treated as certain.
- [ ] 3.4 Preserve acceptable behavior for single-speaker videos and speaker-attribution-disabled jobs.

## 4. Long-video merge behavior

- [ ] 4.1 Extend chunk merge to preserve speaker-labeled segments when attribution is enabled.
- [ ] 4.2 Define how chunk-level speaker drift is represented (for example, downgraded confidence or `unknown`).
- [ ] 4.3 Verify the merge path does not imply false certainty across chunk boundaries.

## 5. Validation

- [ ] 5.1 Add tests covering speaker-aware segment schema and backward compatibility.
- [ ] 5.2 Add validation coverage for single-speaker, multi-speaker short-video, and multi-speaker long-video cases.
- [ ] 5.3 Verify low-confidence speaker assignments remain distinguishable in output artifacts.
- [ ] 5.4 Run `openspec validate --strict` successfully for this change.
