## ADDED Requirements

### Requirement: Preserve speaker-labeled segments through long-video merge
The system SHALL preserve speaker-labeled segment structure through chunked long-video processing when speaker attribution is enabled.

#### Scenario: Merge speaker-aware chunk outputs
- **WHEN** a long video is processed with speaker attribution enabled
- **THEN** the merged transcript artifact SHALL retain speaker-labeled segments rather than collapsing all merged output into unlabeled text

### Requirement: Prefer uncertainty over forced speaker continuity
The system SHALL avoid overstating speaker continuity across chunk boundaries when reconciliation is uncertain.

#### Scenario: Chunk-level speaker mapping drift
- **WHEN** adjacent chunks cannot be reconciled into one confident speaker mapping
- **THEN** the merged transcript artifact SHALL preserve explicit uncertainty or downgraded confidence instead of forcing a misleading continuous speaker identity
