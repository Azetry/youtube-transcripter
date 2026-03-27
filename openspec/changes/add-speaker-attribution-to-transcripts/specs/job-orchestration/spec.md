## ADDED Requirements

### Requirement: Optional speaker-attribution mode
The system SHALL allow transcript jobs to request speaker attribution as an optional processing mode.

#### Scenario: Request speaker-aware processing
- **WHEN** a caller submits a transcription job with speaker attribution enabled
- **THEN** the job configuration and resulting metadata SHALL record that speaker-aware processing was requested

#### Scenario: Default processing remains speaker-agnostic
- **WHEN** a caller submits a transcription job without speaker attribution enabled
- **THEN** the system SHALL preserve the existing speaker-agnostic processing path by default
