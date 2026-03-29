## ADDED Requirements

### Requirement: Explicit speaker-attribution strategy selection
The system SHALL allow callers to explicitly choose the speaker-attribution strategy for a job.

#### Scenario: Request heuristic mode explicitly
- **WHEN** a caller submits a job with the heuristic speaker-attribution strategy selected
- **THEN** the job metadata and resulting artifact metadata SHALL record heuristic mode explicitly

#### Scenario: Request real diarization mode explicitly
- **WHEN** a caller submits a job with the real diarization strategy selected
- **THEN** the job metadata and resulting artifact metadata SHALL record that selected strategy explicitly
