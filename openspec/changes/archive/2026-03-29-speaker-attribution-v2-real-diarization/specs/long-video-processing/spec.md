## ADDED Requirements

### Requirement: Conservative long-video speaker reconciliation
The system SHALL preserve conservative ambiguity handling when reconciling real diarization output across long-video chunk boundaries.

#### Scenario: Ambiguous cross-chunk continuity
- **WHEN** adjacent long-video chunks cannot be reconciled into one confident speaker mapping
- **THEN** the merged artifact SHALL downgrade confidence or mark `unknown` rather than forcing one continuous speaker identity

### Requirement: Long-video diarization remains usable
The system SHALL preserve usable speaker-aware output for the target v2 scope of 2–3 speaker interview/podcast/discussion content.

#### Scenario: Long-form interview sample
- **WHEN** a long-form interview or podcast video is processed with the real diarization strategy
- **THEN** the resulting merged artifact SHALL preserve usable speaker-turn structure for manual acceptance on golden samples
