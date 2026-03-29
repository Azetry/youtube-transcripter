# job-orchestration Specification

## Purpose
TBD - created by archiving change upgrade-transcription-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Shared transcription orchestration
The system SHALL provide one shared transcription orchestration flow that is used by both the CLI and API entrypoints.

#### Scenario: CLI uses shared orchestration
- **WHEN** a user runs the CLI with a valid YouTube URL
- **THEN** the CLI SHALL invoke the shared orchestration service instead of owning a separate end-to-end pipeline

#### Scenario: API uses shared orchestration
- **WHEN** a user submits a transcription job through the API
- **THEN** the API SHALL invoke the same shared orchestration service used by the CLI

### Requirement: Explicit job lifecycle states
The system SHALL track transcription jobs through explicit lifecycle states and expose machine-readable progress metadata.

#### Scenario: Job created
- **WHEN** a new transcription request is accepted
- **THEN** the system SHALL create a job record with a pending state and a unique job identifier

#### Scenario: Job progresses through stages
- **WHEN** a job is being processed
- **THEN** the system SHALL expose progress state including status, stage, and user-readable message

#### Scenario: Job fails
- **WHEN** a processing stage encounters a terminal error
- **THEN** the system SHALL mark the job as failed with an explicit error code and error message

### Requirement: Optional speaker-attribution mode
The system SHALL allow transcript jobs to request speaker attribution as an optional processing mode.

#### Scenario: Request speaker-aware processing
- **WHEN** a caller submits a transcription job with speaker attribution enabled
- **THEN** the job configuration and resulting metadata SHALL record that speaker-aware processing was requested

#### Scenario: Default processing remains speaker-agnostic
- **WHEN** a caller submits a transcription job without speaker attribution enabled
- **THEN** the system SHALL preserve the existing speaker-agnostic processing path by default

### Requirement: Explicit speaker-attribution strategy selection
The system SHALL allow callers to explicitly choose the speaker-attribution strategy for a job.

#### Scenario: Request heuristic mode explicitly
- **WHEN** a caller submits a job with the heuristic speaker-attribution strategy selected
- **THEN** the job metadata and resulting artifact metadata SHALL record heuristic mode explicitly

#### Scenario: Request real diarization mode explicitly
- **WHEN** a caller submits a job with the real diarization strategy selected
- **THEN** the job metadata and resulting artifact metadata SHALL record that selected strategy explicitly

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

