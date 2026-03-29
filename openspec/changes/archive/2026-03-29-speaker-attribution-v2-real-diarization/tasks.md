## 1. Strategy abstraction

- [ ] 1.1 Refactor speaker attribution into an explicit strategy abstraction.
- [ ] 1.2 Keep the current heuristic implementation available as fallback/debug mode.
- [ ] 1.3 Persist strategy identifiers/version metadata through job and artifact models.

## 2. Real post-hoc backend

- [ ] 2.1 Integrate one real post-hoc diarization backend.
- [ ] 2.2 Add translation from backend diarization output into internal speaker-turn structures.
- [ ] 2.3 Preserve explicit uncertainty semantics in the resulting transcript artifacts.

## 3. Alignment and long-video behavior

- [ ] 3.1 Add transcript-segment ↔ speaker-turn alignment logic.
- [ ] 3.2 Harden chunk-boundary ambiguity handling for long videos.
- [ ] 3.3 Ensure ambiguous continuity downgrades confidence or marks `unknown` instead of forcing continuity.

## 4. Operator surface

- [ ] 4.1 Add explicit strategy selection to CLI/API request surfaces.
- [ ] 4.2 Surface strategy metadata clearly in artifact outputs and responses.
- [ ] 4.3 Document heuristic vs real diarization usage and limitations.

## 5. Validation

- [ ] 5.1 Define golden-video acceptance coverage for 2–3 speaker interview/podcast samples.
- [ ] 5.2 Validate multilingual / mixed-language behavior on selected samples.
- [ ] 5.3 Add benchmark scaffolding or scorecard hooks after initial manual acceptance.
- [ ] 5.4 Run `openspec validate --strict` successfully for this change.
