## Why

`youtube-transcripter` now has a solid upgraded transcript pipeline, but real-world YouTube acquisition on this host remains unreliable. The same repo/commit works on Azetry's local machine, which strongly suggests an environment/IP/client-strategy problem rather than a transcript-pipeline defect.

We need a follow-up change focused specifically on acquisition robustness: improve this host's success rate, classify failures cleanly, and provide an operational fallback to an alternate always-on acquisition host when this host is blocked.

## What Changes

- Add a clearer acquisition strategy layer for this host (unauthenticated-first hardening, authenticated modes, and classified failure handling).
- Introduce explicit acquisition operating modes: this-host extraction, alternate-host extraction, and manual handoff.
- Add a semi-automatic fallback model that prioritizes an alternate always-on host before Azetry's local machine.
- Add diagnostics and operator-visible fallback reasoning so extraction failures are actionable rather than opaque yt-dlp traces.
- Keep transcript-pipeline responsibilities distinct from acquisition-host responsibilities.

## Capabilities

### New Capabilities
- `youtube-acquisition-modes`: Distinct acquisition modes and fallback order for YouTube extraction.
- `youtube-acquisition-diagnostics`: Classified extractor diagnostics and actionable failure guidance.
- `alternate-acquisition-host`: URL-based remote acquisition fallback to an alternate always-on host.

### Modified Capabilities
- `job-orchestration`: Extend orchestration to support acquisition mode selection/fallback before transcript processing begins.

## Impact

- Affected code: extractor, orchestration/service layer, operational config, and likely follow-up runbook/docs.
- New design concern: this host may no longer be assumed to be the only acquisition executor.
- Operational impact: alternate always-on VM becomes a first-class fallback target for blocked YouTube extraction.
