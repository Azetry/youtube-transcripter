## ADDED Requirements

### Requirement: Explicit acquisition modes
The system SHALL support explicit YouTube acquisition modes for this-host extraction, alternate-host extraction, and manual handoff.

#### Scenario: This-host extraction selected
- **WHEN** YouTube acquisition is attempted locally on the current host
- **THEN** the system SHALL classify the attempt as `this-host` mode

#### Scenario: Alternate-host extraction selected
- **WHEN** the system routes a YouTube URL to an alternate always-on acquisition host
- **THEN** the system SHALL classify the attempt as `alternate-host` mode

#### Scenario: Manual handoff selected
- **WHEN** the operator chooses to bypass automated extraction and provide media/artifacts manually
- **THEN** the system SHALL classify the attempt as `manual-handoff` mode

### Requirement: Preferred fallback order
The system SHALL prefer an alternate always-on host before Azetry's local machine when this host cannot reliably extract YouTube.

#### Scenario: This host blocked
- **WHEN** extraction on this host is classified as blocked or unreliable
- **THEN** the system SHALL prefer the configured alternate always-on host as the next fallback target before recommending Azetry's local machine
