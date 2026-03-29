## ADDED Requirements

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
