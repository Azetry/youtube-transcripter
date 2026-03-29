# long-video-processing Specification

## Purpose
TBD - created by archiving change upgrade-transcription-pipeline. Update Purpose after archive.
## Requirements
### Requirement: Long-video chunking with overlap
The system SHALL support processing videos that exceed the single-file transcription limit by chunking audio into deterministic overlapping segments.

#### Scenario: Chunk long video
- **WHEN** a video's audio exceeds the single-file transcription limit or configured chunk threshold
- **THEN** the system SHALL generate chunk files using deterministic time-based chunking

#### Scenario: Use initial overlap policy
- **WHEN** the initial long-video strategy is used
- **THEN** the system SHALL use a default target chunk size of 10 minutes and overlap adjacent chunks by 15 seconds

### Requirement: Timestamp-aware merge
The system SHALL merge chunk transcripts using segment timestamps mapped onto a global timeline.

#### Scenario: Merge chunk segments globally
- **WHEN** chunk-level transcripts include timestamped segments
- **THEN** the system SHALL convert chunk-relative timestamps into global timestamps before building merged outputs

### Requirement: Overlap deduplication
The system SHALL avoid obvious duplicate transcript content in overlap regions.

#### Scenario: Remove duplicate overlap content
- **WHEN** adjacent chunks contain overlapping transcript content for the same spoken region
- **THEN** the system SHALL deduplicate overlap content using timestamp overlap as the primary signal and normalized text similarity as a secondary safeguard

### Requirement: Chunk-level correction with final consistency pass
The system SHALL support chunk-level correction followed by a merged consistency pass for long-form transcripts.

#### Scenario: Correct chunk first then merge
- **WHEN** a long video is processed
- **THEN** the system SHALL produce corrected chunk outputs before generating the merged transcript

#### Scenario: Run final consistency pass
- **WHEN** chunk outputs have been merged into a final transcript
- **THEN** the system SHALL run a lightweight consistency pass without aggressively rewriting source meaning

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

