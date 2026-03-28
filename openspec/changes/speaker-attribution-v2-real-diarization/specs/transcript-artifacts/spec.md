## ADDED Requirements

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
