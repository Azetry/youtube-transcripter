## Why

`youtube-transcripter` now produces durable transcript artifacts, but interview/podcast-style content still collapses all speech into a single stream. That loses who-said-what structure, weakens quote extraction, and forces downstream agents to infer turn-taking from plain text.

We need a follow-up change that adds speaker-aware transcript artifacts while keeping the repo's boundary clean: `youtube-transcripter` should remain a transcript artifact generator, not become an article generator or a full identity-resolution system.

## What Changes

- Add optional speaker-attribution mode for transcript jobs.
- Extend canonical transcript JSON artifacts to carry segment-level speaker metadata and attribution confidence.
- Support conservative speaker labeling for interview/podcast/discussion content using generic labels such as `Speaker A/B/C`.
- Preserve compatibility for existing single-speaker and non-speaker-aware transcript outputs.
- Extend long-video merge behavior so speaker-labeled segments survive chunking/merge without pretending to solve hard multi-party overlap cases.

## Capabilities

### New Capabilities
- `speaker-attributed-transcript-artifacts`: Structured transcript artifacts with segment-level speaker metadata and uncertainty.

### Modified Capabilities
- `transcript-artifacts`: Canonical transcript outputs now optionally carry speaker metadata.
- `long-video-processing`: Chunk merge now preserves speaker-labeled segments when speaker attribution is enabled.
- `job-orchestration`: Jobs can request optional speaker attribution and surface that strategy in job metadata.

## Impact

- Affected code: transcription/correction pipeline, artifact schema/models, chunk merge logic, CLI/API request surface, and persistence/storage models.
- New design concern: speaker attribution must remain conservative and explicit about uncertainty.
- Boundary decision: named host/guest resolution and article generation remain out of scope for this change.
