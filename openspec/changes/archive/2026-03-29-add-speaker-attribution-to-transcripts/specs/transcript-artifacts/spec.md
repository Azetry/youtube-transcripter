## ADDED Requirements

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
