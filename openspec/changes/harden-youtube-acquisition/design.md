## Context

The upgraded transcript pipeline (A–E) now works in tests and on Azetry's local machine, but this host repeatedly fails against real YouTube URLs with errors such as `Sign in to confirm you're not a bot` and `The page needs to be reloaded`, even after authenticated cookie support was added. This means the remaining reliability issue is primarily in YouTube acquisition on this host.

The design goal is not to promise universal no-cookie extraction. Instead, it is to (1) improve this host's acquisition success rate, (2) classify failures accurately, and (3) provide a practical alternate-host fallback that does not depend on Azetry's local machine being online 24/7.

## Goals / Non-Goals

**Goals:**
- Improve acquisition robustness on this host without destabilizing the transcript pipeline.
- Define explicit acquisition modes and fallback order.
- Surface actionable extraction diagnostics and operator-visible reasons for fallback.
- Support an alternate always-on VM as the preferred fallback acquisition host.
- Prefer URL + remote acquisition request handoff over large file handoff as the primary fallback shape.

**Non-Goals:**
- Rebuilding the transcript pipeline again.
- Frontend redesign.
- Heavy anti-bot/proxy rotation infrastructure by default.
- Fully automating external account login in Azetry's name.
- Immediate OpenSpec archive of the earlier upgrade change.

## Decisions

### 1. Dual-track strategy
The system will pursue both:
- improving this host's success rate, and
- providing alternate-host fallback when this host is blocked.

**Why:** Relying only on hardening this host is too brittle; relying only on fallback hides local regressions. Both are needed.

### 2. Alternate always-on host is the preferred fallback
When this host is blocked, the preferred fallback target is an alternate always-on VM rather than Azetry's local machine.

**Why:** Azetry's local machine may not be online 24/7.

### 3. URL-based remote acquisition request first
Fallback handoff should primarily be URL + remote acquisition request metadata, not large raw media transfer.

**Why:** It keeps the system boundary cleaner and reduces artifact-transfer overhead.

### 4. Semi-automatic fallback UX
The system should classify the failure and choose/recommend the next acquisition mode, while making the decision visible in logs/operator output.

**Why:** Fully manual fallback is too slow; fully silent fallback is too opaque.

### 5. Keep acquisition and transcript responsibilities separate
Acquisition reliability work should remain localized to extractor/orchestration/fallback logic rather than re-entangling the transcript pipeline.

**Why:** The transcript pipeline is already in a good state and should not be destabilized.

## Risks / Trade-offs

- Host-specific hardening may still not fully overcome YouTube/IP reputation issues.
- Alternate-host fallback introduces more operational moving parts.
- URL-based remote acquisition requires a clean trust/contract boundary between pipeline host and acquisition host.
- Semi-automatic fallback must be visible enough to debug without becoming noisy.

## Migration / Delivery shape

Recommended delivery order:
1. Add failure classification and acquisition mode model.
2. Add fallback-selection logic and diagnostics.
3. Add alternate-host request contract / runner integration.
4. Add operator-facing runbook for how this host, alternate host, and manual fallback relate.

This allows incremental value before attempting full remote-executor polish.
