## ADDED Requirements

### Requirement: Jobs persist across restarts
The system SHALL persist completed and failed job records so they remain queryable after process restart.

#### Scenario: Completed job survives restart
- **WHEN** a transcription job completes and the API process restarts
- **THEN** the system SHALL still return the stored job status and result metadata for that job

#### Scenario: Failed job survives restart
- **WHEN** a transcription job fails and the API process restarts
- **THEN** the system SHALL still return the failed status and stored error metadata for that job

### Requirement: Exact-input reuse
The system SHALL reuse a previously completed job only when the new request matches the prior job's normalized input signature exactly.

#### Scenario: Reuse exact-matching request
- **WHEN** a new transcription request matches a completed job's normalized URL, language, correction settings, custom terms, and strategy versions
- **THEN** the system SHALL return a reuse decision tied to the existing completed job instead of creating a different result silently

#### Scenario: Do not reuse changed-strategy request
- **WHEN** a new transcription request matches the same URL but chunking or correction strategy versions differ
- **THEN** the system SHALL treat the request as a new job or require an explicit rerun path
