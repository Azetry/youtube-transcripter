## 1. Acquisition mode model and diagnostics

- [ ] 1.1 Define explicit acquisition modes: this-host, alternate-host, manual handoff.
- [ ] 1.2 Define a small extraction-failure classification model (unauthenticated block, authenticated block, page-reload/client-strategy issue, network/IP issue, unavailable video, unknown).
- [ ] 1.3 Surface classified failure diagnostics through the orchestration/service layer.

## 2. This-host robustness improvements

- [ ] 2.1 Refine extractor/orchestration to try approved best-effort local strategies in a controlled order.
- [ ] 2.2 Ensure authenticated extraction modes and unauthenticated-first logic remain backward compatible.
- [ ] 2.3 Add tests for failure classification and strategy selection.

## 3. Alternate-host fallback

- [ ] 3.1 Define URL-based remote acquisition request contract.
- [ ] 3.2 Add fallback-selection logic that prioritizes the alternate always-on host before local-machine fallback.
- [ ] 3.3 Add operator-visible logging/output describing when and why fallback occurred.

## 4. Operational clarity

- [ ] 4.1 Document how to configure and use the alternate acquisition host.
- [ ] 4.2 Document the fallback order and what each acquisition mode is responsible for.
- [ ] 4.3 Validate that future sessions can tell whether to retry locally, retry with auth, or switch to alternate host.

## 5. Validation

- [ ] 5.1 Add tests covering failure classification and fallback routing decisions.
- [ ] 5.2 Verify this-host extraction behavior remains unchanged when fallback is disabled/unconfigured.
- [ ] 5.3 Validate the OpenSpec change with `openspec validate --strict`.
