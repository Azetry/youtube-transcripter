## ADDED Requirements

### Requirement: URL-based remote acquisition handoff
The system SHALL support a URL-based handoff to an alternate acquisition host rather than requiring large media transfer as the primary fallback shape.

#### Scenario: Remote acquisition request created
- **WHEN** the alternate-host fallback mode is selected
- **THEN** the system SHALL produce a URL-based acquisition request contract suitable for the alternate host to execute

### Requirement: Separation of acquisition and transcript responsibilities
The system SHALL keep acquisition-host responsibilities distinct from transcript-pipeline responsibilities.

#### Scenario: Alternate host handles acquisition
- **WHEN** an alternate host is used for YouTube acquisition
- **THEN** the system SHALL keep the acquisition step logically separable from later transcript-pipeline execution so the operating boundary remains understandable
