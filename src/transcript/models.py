"""Segment and merge-result models for the transcript merger.

These models represent the intermediate and final data structures used
when merging chunk-level transcripts into a single global transcript.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Segment:
    """A single timestamped segment of transcript text.

    Timestamps are always in *global* (full-video) seconds once they
    have passed through the merger.  Before mapping, they may be
    chunk-relative.
    """
    start: float
    end: float
    text: str


@dataclass
class ChunkTranscript:
    """All transcript outputs for one audio chunk.

    Attributes:
        chunk_index: Zero-based chunk index matching ChunkPlan.
        chunk_start: Global start time of this chunk in seconds.
        chunk_end: Global end time of this chunk in seconds.
        segments: Timestamped segments with *chunk-relative* times.
        raw_text: Full raw (uncorrected) text for this chunk.
        corrected_text: Full corrected text for this chunk.
    """
    chunk_index: int
    chunk_start: float
    chunk_end: float
    segments: list[Segment]
    raw_text: str
    corrected_text: str


@dataclass
class MergedTranscript:
    """The result of merging all chunk transcripts.

    Attributes:
        segments: Deduplicated segments with global timestamps.
        raw_text: Concatenated raw text after dedup.
        corrected_text: Concatenated corrected text after dedup.
        consistency_text: Corrected text after final consistency pass
            (empty string if no pass was run).
        chunk_count: Number of source chunks merged.
        segments_before_dedup: Total segment count before dedup.
        segments_after_dedup: Total segment count after dedup.
        overlap_regions_processed: Number of overlap boundaries handled.
    """
    segments: list[Segment]
    raw_text: str
    corrected_text: str
    consistency_text: str = ""
    chunk_count: int = 0
    segments_before_dedup: int = 0
    segments_after_dedup: int = 0
    overlap_regions_processed: int = 0
