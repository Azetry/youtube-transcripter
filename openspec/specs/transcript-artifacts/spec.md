# transcript-artifacts Specification

## Purpose
TBD - created by archiving change upgrade-transcription-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Stable transcript result schema
The system SHALL expose a stable transcript result schema covering request input, video metadata, lifecycle state, and transcript artifacts.

#### Scenario: Return stable result structure
- **WHEN** a job is queried after processing begins or completes
- **THEN** the system SHALL return a structured result containing job metadata, request metadata, and available artifacts in a predictable shape

### Requirement: Reviewable raw and corrected outputs
The system SHALL retain both raw transcript output and corrected transcript output for review.

#### Scenario: Store both transcript forms
- **WHEN** a transcription job completes successfully
- **THEN** the system SHALL retain references to both the original transcript and corrected transcript outputs

### Requirement: Diff summary artifact
The system SHALL produce a diff artifact or summary that makes transcript correction changes reviewable.

#### Scenario: Return diff metadata
- **WHEN** a transcription job completes successfully
- **THEN** the system SHALL make a diff summary or diff artifact path available as part of the persisted result

### Requirement: Timestamped segment artifacts
The system SHALL retain timestamped segment artifacts for downstream workflows.

#### Scenario: Persist merged segments
- **WHEN** timestamp-enabled transcription is available
- **THEN** the system SHALL persist segment artifacts with timestamps that downstream workflows can reference

### Requirement: Speaker-aware transcript artifact schema
The system SHALL support a canonical structured transcript artifact that can optionally include segment-level speaker metadata.

#### Scenario: Return speaker-aware segments in canonical JSON
- **WHEN** a transcription job completes with speaker attribution enabled
- **THEN** the canonical transcript artifact SHALL expose segment entries containing time bounds, text, and speaker metadata in a predictable machine-readable shape

### Requirement: Explicit speaker-attribution uncertainty
The system SHALL represent speaker-attribution certainty explicitly rather than implying all speaker labels are equally reliable.

#### Scenario: Mark low-confidence speaker assignment
- **WHEN** the system assigns a speaker label with limited confidence
- **THEN** the canonical transcript artifact SHALL include confidence and/or attribution-mode metadata that distinguishes tentative attribution from confident attribution

### Requirement: Backward-compatible transcript outputs
The system SHALL preserve usable transcript outputs when speaker attribution is disabled or unnecessary.

#### Scenario: Preserve speaker-agnostic transcript behavior
- **WHEN** a job is processed without speaker attribution enabled
- **THEN** the system SHALL continue to produce usable transcript outputs without requiring speaker metadata to exist on every segment

### Requirement: Strategy-aware speaker attribution artifacts
The system SHALL expose which speaker-attribution strategy produced a speaker-aware transcript artifact.

#### Scenario: Return strategy metadata in artifact output
- **WHEN** a job completes with speaker attribution enabled
- **THEN** the resulting transcript artifact SHALL include strategy metadata that identifies whether heuristic or real diarization produced the speaker labels

### Requirement: Real diarization-backed speaker turns
The system SHALL support at least one real non-heuristic speaker-attribution strategy.

#### Scenario: Produce non-heuristic speaker-aware transcript artifact
- **WHEN** a job is run with the real diarization strategy selected
- **THEN** the transcript artifact SHALL include speaker-labeled segments produced from that real diarization path

### Requirement: Explicit uncertainty remains required
The system SHALL preserve explicit uncertainty semantics even when a real diarization backend is used.

#### Scenario: Ambiguous speaker assignment
- **WHEN** the system cannot confidently assign a transcript segment to one speaker
- **THEN** the transcript artifact SHALL express downgraded confidence or `unknown` behavior rather than implying false certainty

