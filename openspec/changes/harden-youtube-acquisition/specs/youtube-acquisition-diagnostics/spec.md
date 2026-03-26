## ADDED Requirements

### Requirement: Classified acquisition failures
The system SHALL classify YouTube acquisition failures into a small actionable set rather than exposing only raw extractor stack traces.

#### Scenario: Unauthenticated block
- **WHEN** extraction fails with signs of bot detection or sign-in requirement without auth configured
- **THEN** the system SHALL classify the failure as an unauthenticated block and surface actionable guidance

#### Scenario: Authenticated block or page-reload issue
- **WHEN** extraction fails even with cookies/auth configured, or with a page-reload/client-strategy style error
- **THEN** the system SHALL classify the failure into a more specific actionable category than a generic unknown error

### Requirement: Operator-visible fallback reasoning
The system SHALL expose why a fallback recommendation or routing decision was made.

#### Scenario: Fallback recommended
- **WHEN** the system decides or recommends switching away from this-host extraction
- **THEN** the operator SHALL be able to see the high-level reason category that triggered the fallback
