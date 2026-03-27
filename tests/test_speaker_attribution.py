"""Tests for speaker attribution pipeline and backward compatibility.

Covers:
    - Pause-based heuristic attribution (short video)
    - Speaker-aware merge (long video / multi-chunk)
    - Chunk boundary uncertainty marking
    - Backward compatibility (attribution disabled)
    - Schema validation of speaker segment structure
    - Low-confidence assignments distinguishable in output
"""

import pytest

from src.transcript.models import Segment, SpeakerInfo, ChunkTranscript
from src.transcript.speaker_attribution import (
    STRATEGY_ID,
    attribute_speakers,
    count_speakers,
    segments_to_dicts,
)
from src.transcript.merger import (
    map_to_global_timeline,
    merge_chunks,
    mark_chunk_boundary_uncertainty,
)


# ── Helpers ────────────────────────────────────────────────────────


def _make_segments(specs: list[tuple[float, float, str]]) -> list[Segment]:
    """Create segments from (start, end, text) tuples."""
    return [Segment(start=s, end=e, text=t) for s, e, t in specs]


# ── Attribution tests ──────────────────────────────────────────────


class TestAttributeSpeakers:
    def test_empty_segments(self):
        result = attribute_speakers([])
        assert result == []

    def test_single_segment(self):
        segs = _make_segments([(0.0, 5.0, "Hello world")])
        result = attribute_speakers(segs)
        assert len(result) == 1
        assert result[0].speaker is not None
        assert result[0].speaker.label == "Speaker A"
        assert result[0].speaker.attribution_mode == "predicted"
        assert 0.0 <= result[0].speaker.confidence <= 1.0

    def test_no_pause_same_speaker(self):
        """Consecutive segments with small gaps stay as same speaker."""
        segs = _make_segments([
            (0.0, 3.0, "First part"),
            (3.0, 6.0, "Second part"),
            (6.5, 9.0, "Third part"),  # 0.5s gap — below threshold
        ])
        result = attribute_speakers(segs)
        assert all(s.speaker.label == "Speaker A" for s in result)

    def test_pause_triggers_speaker_change(self):
        """A gap >= 2s triggers a speaker change."""
        segs = _make_segments([
            (0.0, 3.0, "Speaker A says this"),
            (5.5, 8.0, "Someone else responds"),  # 2.5s gap
            (8.0, 11.0, "Continues"),
        ])
        result = attribute_speakers(segs)
        assert result[0].speaker.label == "Speaker A"
        assert result[1].speaker.label == "Speaker B"
        assert result[2].speaker.label == "Speaker B"

    def test_multiple_speaker_changes(self):
        segs = _make_segments([
            (0.0, 3.0, "A speaks"),
            (6.0, 9.0, "B speaks"),     # 3s gap
            (12.0, 15.0, "C speaks"),   # 3s gap
        ])
        result = attribute_speakers(segs)
        labels = [s.speaker.label for s in result]
        assert labels == ["Speaker A", "Speaker B", "Speaker C"]

    def test_chunk_index_attached(self):
        segs = _make_segments([(0.0, 5.0, "test")])
        result = attribute_speakers(segs, chunk_index=3)
        assert result[0].chunk_index == 3

    def test_all_attributions_are_predicted(self):
        segs = _make_segments([
            (0.0, 3.0, "first"),
            (6.0, 9.0, "second"),
        ])
        result = attribute_speakers(segs)
        for seg in result:
            assert seg.speaker.attribution_mode == "predicted"

    def test_short_segment_lower_confidence(self):
        """Segments < 1s should get lower confidence."""
        segs = _make_segments([(0.0, 0.5, "hmm")])
        result = attribute_speakers(segs)
        assert result[0].speaker.confidence < 0.4

    def test_long_segment_higher_confidence(self):
        """Segments > 5s should get slightly higher confidence."""
        segs = _make_segments([(0.0, 8.0, "a long sentence here")])
        result = attribute_speakers(segs)
        assert result[0].speaker.confidence > 0.4


class TestCountSpeakers:
    def test_count_distinct(self):
        segs = [
            Segment(0, 3, "a", SpeakerInfo("Speaker A", 0.4, "predicted")),
            Segment(5, 8, "b", SpeakerInfo("Speaker B", 0.4, "predicted")),
            Segment(8, 11, "c", SpeakerInfo("Speaker A", 0.4, "predicted")),
        ]
        assert count_speakers(segs) == 2

    def test_no_speakers(self):
        segs = _make_segments([(0, 3, "no speaker info")])
        assert count_speakers(segs) == 0


class TestSegmentsToDicts:
    def test_serialization(self):
        speaker = SpeakerInfo("Speaker A", 0.4, "predicted")
        segs = [Segment(1.0, 3.0, "hello", speaker, chunk_index=0)]
        dicts = segments_to_dicts(segs)
        assert len(dicts) == 1
        d = dicts[0]
        assert d["start"] == 1.0
        assert d["end"] == 3.0
        assert d["text"] == "hello"
        assert d["speaker"]["label"] == "Speaker A"
        assert d["speaker"]["confidence"] == 0.4
        assert d["speaker"]["attribution_mode"] == "predicted"
        assert d["chunk_index"] == 0

    def test_without_speaker(self):
        segs = [Segment(0.0, 1.0, "bare")]
        dicts = segments_to_dicts(segs)
        assert "speaker" not in dicts[0]


# ── Merger speaker preservation tests ──────────────────────────────


class TestMergerSpeakerPreservation:
    def test_global_timeline_preserves_speaker(self):
        speaker = SpeakerInfo("Speaker A", 0.4, "predicted")
        chunk = ChunkTranscript(
            chunk_index=0,
            chunk_start=100.0,
            chunk_end=200.0,
            segments=[Segment(5.0, 10.0, "hello", speaker, chunk_index=0)],
            raw_text="hello",
            corrected_text="hello",
        )
        mapped = map_to_global_timeline(chunk)
        assert len(mapped) == 1
        assert mapped[0].start == 105.0
        assert mapped[0].end == 110.0
        assert mapped[0].speaker is not None
        assert mapped[0].speaker.label == "Speaker A"
        assert mapped[0].chunk_index == 0

    def test_global_timeline_preserves_none_speaker(self):
        """When no speaker info, field stays None."""
        chunk = ChunkTranscript(
            chunk_index=0,
            chunk_start=0.0,
            chunk_end=100.0,
            segments=[Segment(0.0, 5.0, "no speaker")],
            raw_text="no speaker",
            corrected_text="no speaker",
        )
        mapped = map_to_global_timeline(chunk)
        assert mapped[0].speaker is None


# ── Chunk boundary uncertainty tests ───────────────────────────────


class TestChunkBoundaryUncertainty:
    def test_single_chunk_unchanged(self):
        speaker = SpeakerInfo("Speaker A", 0.4, "predicted")
        segs = [Segment(0, 5, "hello", speaker, chunk_index=0)]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=1)
        assert result[0].speaker.attribution_mode == "predicted"

    def test_first_chunk_unchanged(self):
        speaker = SpeakerInfo("Speaker A", 0.4, "predicted")
        segs = [
            Segment(0, 5, "chunk 0 seg", speaker, chunk_index=0),
            Segment(600, 605, "chunk 1 seg", speaker, chunk_index=1),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=2)
        # First chunk's segment unchanged
        assert result[0].speaker.attribution_mode == "predicted"
        # Second chunk's first segment marked unknown
        assert result[1].speaker.attribution_mode == "unknown"
        assert result[1].speaker.confidence == 0.1

    def test_second_segment_of_second_chunk_unchanged(self):
        speaker = SpeakerInfo("Speaker B", 0.4, "predicted")
        segs = [
            Segment(0, 5, "chunk 0", SpeakerInfo("Speaker A", 0.4, "predicted"), chunk_index=0),
            Segment(600, 605, "chunk 1 first", speaker, chunk_index=1),
            Segment(605, 610, "chunk 1 second", speaker, chunk_index=1),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=2)
        # Only first segment of chunk 1 is unknown
        assert result[1].speaker.attribution_mode == "unknown"
        assert result[2].speaker.attribution_mode == "predicted"

    def test_no_speaker_metadata_skipped(self):
        """Segments without speaker info are not modified."""
        segs = [
            Segment(0, 5, "no speaker", chunk_index=0),
            Segment(600, 605, "also no speaker", chunk_index=1),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=2)
        assert result[0].speaker is None
        assert result[1].speaker is None


# ── Backward compatibility tests ───────────────────────────────────


class TestBackwardCompatibility:
    def test_segment_without_speaker_unchanged(self):
        """Existing code creating Segment(start, end, text) still works."""
        seg = Segment(1.0, 2.0, "test")
        assert seg.speaker is None
        assert seg.chunk_index is None

    def test_merge_without_speakers(self):
        """Standard merge pipeline works unchanged when no speaker metadata."""
        chunks = [
            ChunkTranscript(
                chunk_index=0,
                chunk_start=0.0,
                chunk_end=100.0,
                segments=[Segment(0.0, 50.0, "first chunk text")],
                raw_text="first chunk text",
                corrected_text="First chunk text.",
            ),
            ChunkTranscript(
                chunk_index=1,
                chunk_start=85.0,
                chunk_end=200.0,
                segments=[Segment(0.0, 50.0, "second chunk text")],
                raw_text="second chunk text",
                corrected_text="Second chunk text.",
            ),
        ]
        merged = merge_chunks(chunks)
        assert merged.chunk_count == 2
        # All segments should have no speaker info
        for seg in merged.segments:
            assert seg.speaker is None

    def test_speaker_info_to_dict(self):
        info = SpeakerInfo("Speaker A", 0.5, "predicted")
        d = info.to_dict()
        assert d == {
            "label": "Speaker A",
            "confidence": 0.5,
            "attribution_mode": "predicted",
        }


# ── Integration: full speaker-aware merge ──────────────────────────


class TestSpeakerAwareMerge:
    def test_two_chunk_merge_with_speakers(self):
        """Simulate a two-chunk merge where each chunk has speaker segments."""
        # Chunk 0: Speaker A then B
        chunk0_segs = attribute_speakers(
            _make_segments([
                (0.0, 10.0, "A speaks in chunk 0"),
                (13.0, 20.0, "B speaks in chunk 0"),  # 3s gap
            ]),
            chunk_index=0,
        )
        # Chunk 1: Speaker C (3s gap from start = new speaker)
        chunk1_segs = attribute_speakers(
            _make_segments([
                (0.0, 10.0, "speaker in chunk 1"),
                (13.0, 20.0, "another in chunk 1"),
            ]),
            chunk_index=1,
        )

        chunks = [
            ChunkTranscript(
                chunk_index=0,
                chunk_start=0.0,
                chunk_end=30.0,
                segments=chunk0_segs,
                raw_text="A speaks in chunk 0 B speaks in chunk 0",
                corrected_text="A speaks. B speaks.",
            ),
            ChunkTranscript(
                chunk_index=1,
                chunk_start=25.0,
                chunk_end=55.0,
                segments=chunk1_segs,
                raw_text="speaker in chunk 1 another in chunk 1",
                corrected_text="Speaker in chunk 1. Another in chunk 1.",
            ),
        ]

        merged = merge_chunks(chunks)
        assert merged.chunk_count == 2

        # All merged segments should preserve speaker metadata
        for seg in merged.segments:
            assert seg.speaker is not None

        # Mark chunk boundaries
        marked = mark_chunk_boundary_uncertainty(merged.segments, 2)
        # Find first segment from chunk 1
        chunk1_segs_in_merged = [s for s in marked if s.chunk_index == 1]
        if chunk1_segs_in_merged:
            assert chunk1_segs_in_merged[0].speaker.attribution_mode == "unknown"

    def test_low_confidence_distinguishable(self):
        """Verify that low-confidence assignments are clearly marked."""
        segs = _make_segments([
            (0.0, 0.3, "uh"),        # Very short → lower confidence
            (5.0, 12.0, "long talk"), # Long → higher confidence
        ])
        result = attribute_speakers(segs)
        short_conf = result[0].speaker.confidence
        long_conf = result[1].speaker.confidence
        assert short_conf < long_conf
        # Both are "predicted" (not "confident")
        assert all(s.speaker.attribution_mode == "predicted" for s in result)
