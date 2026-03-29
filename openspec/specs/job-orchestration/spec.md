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

