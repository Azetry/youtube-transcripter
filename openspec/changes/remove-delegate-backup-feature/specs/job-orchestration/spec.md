## ADDED Requirements

### Requirement: No remote full-pipeline backup delegation
The system SHALL NOT call a separate backup HTTP service to run the full transcription pipeline when this-host YouTube acquisition fails or when otherwise configured via `BACKUP_SERVICE_URL`.

#### Scenario: Local acquisition fails
- **WHEN** structured this-host acquisition exhausts configured strategies without success
- **THEN** the orchestration SHALL fail locally with operator-visible diagnostics
- **AND** SHALL NOT send an HTTP request to a backup service to complete transcription

#### Scenario: No backup delegation environment
- **WHEN** operators deploy the application
- **THEN** they SHALL NOT be required to configure `BACKUP_SERVICE_URL` or `BACKUP_SERVICE_TOKEN` for core transcription behavior

### Requirement: No delegate transcription HTTP API
The system SHALL NOT expose HTTP routes whose sole purpose is accepting delegated full-pipeline transcription jobs from another service instance (e.g. `POST /delegate/transcribe`).

#### Scenario: API surface
- **WHEN** the FastAPI application starts
- **THEN** it SHALL NOT register delegate transcription endpoints described by the removed backup delegation feature
