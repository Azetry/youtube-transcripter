"""Tests for speaker attribution pipeline and backward compatibility.

Covers:
    - Pause-based heuristic attribution (short video)
    - Pyannote post-hoc diarization strategy (mocked)
    - Strategy registry (get_strategy / list_strategies)
    - Alignment helper (_align_segments_to_turns)
    - Speaker-aware merge (long video / multi-chunk)
    - Chunk boundary uncertainty marking
    - Backward compatibility (attribution disabled)
    - Schema validation of speaker segment structure
    - Low-confidence assignments distinguishable in output
"""

from unittest.mock import MagicMock, patch

import pytest

from src.transcript.models import Segment, SpeakerInfo, ChunkTranscript
from src.transcript.speaker_attribution import (
    AMBIGUITY_MARGIN,
    MIN_OVERLAP_RATIO,
    PYANNOTE_STRATEGY_ID,
    STRATEGY_ID,
    AttributionResult,
    PyannoteStrategy,
    _align_segments_to_turns,
    attribute_speakers,
    count_speakers,
    describe_strategies,
    get_strategy,
    list_strategies,
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

    def test_two_chunks_boundary_segments_marked(self):
        """With two chunks, last seg of chunk 0 and first seg of chunk 1 are marked."""
        speaker = SpeakerInfo("Speaker A", 0.4, "predicted")
        segs = [
            Segment(0, 5, "chunk 0 seg", speaker, chunk_index=0),
            Segment(600, 605, "chunk 1 seg", speaker, chunk_index=1),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=2)
        # Last (only) segment of chunk 0 marked unknown (trailing edge)
        assert result[0].speaker.attribution_mode == "unknown"
        assert result[0].speaker.confidence == 0.1
        # First segment of chunk 1 marked unknown (leading edge)
        assert result[1].speaker.attribution_mode == "unknown"
        assert result[1].speaker.confidence == 0.1

    def test_interior_segments_unchanged(self):
        """Interior segments (not at chunk edges) stay unchanged."""
        speaker = SpeakerInfo("Speaker B", 0.4, "predicted")
        segs = [
            Segment(0, 5, "chunk 0 first", SpeakerInfo("Speaker A", 0.4, "predicted"), chunk_index=0),
            Segment(5, 10, "chunk 0 last", SpeakerInfo("Speaker A", 0.4, "predicted"), chunk_index=0),
            Segment(600, 605, "chunk 1 first", speaker, chunk_index=1),
            Segment(605, 610, "chunk 1 second", speaker, chunk_index=1),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=2)
        # First seg of chunk 0: unchanged (first chunk leading edge not marked)
        assert result[0].speaker.attribution_mode == "predicted"
        # Last seg of chunk 0: marked unknown (trailing edge)
        assert result[1].speaker.attribution_mode == "unknown"
        # First seg of chunk 1: marked unknown (leading edge)
        assert result[2].speaker.attribution_mode == "unknown"
        # Second seg of chunk 1: unchanged (interior of last chunk)
        assert result[3].speaker.attribution_mode == "predicted"

    def test_no_speaker_metadata_skipped(self):
        """Segments without speaker info are not modified."""
        segs = [
            Segment(0, 5, "no speaker", chunk_index=0),
            Segment(600, 605, "also no speaker", chunk_index=1),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=2)
        assert result[0].speaker is None
        assert result[1].speaker is None

    def test_three_chunks_middle_both_edges_marked(self):
        """For a middle chunk, both first and last segments are marked."""
        speaker = SpeakerInfo("Speaker A", 0.8, "confident")
        segs = [
            Segment(0, 5, "c0 only", speaker, chunk_index=0),
            Segment(600, 605, "c1 first", speaker, chunk_index=1),
            Segment(605, 610, "c1 middle", speaker, chunk_index=1),
            Segment(610, 615, "c1 last", speaker, chunk_index=1),
            Segment(1200, 1205, "c2 only", speaker, chunk_index=2),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=3)
        # c0 last (=only): trailing edge → unknown
        assert result[0].speaker.attribution_mode == "unknown"
        # c1 first: leading edge → unknown
        assert result[1].speaker.attribution_mode == "unknown"
        # c1 middle: interior → unchanged
        assert result[2].speaker.attribution_mode == "confident"
        # c1 last: trailing edge → unknown
        assert result[3].speaker.attribution_mode == "unknown"
        # c2 first (=only): leading edge → unknown
        assert result[4].speaker.attribution_mode == "unknown"

    def test_boundary_preserves_label(self):
        """Marking preserves original speaker label for reviewability."""
        speaker = SpeakerInfo("Speaker B", 0.9, "confident")
        segs = [
            Segment(0, 5, "c0", speaker, chunk_index=0),
            Segment(600, 605, "c1", speaker, chunk_index=1),
        ]
        result = mark_chunk_boundary_uncertainty(segs, chunk_count=2)
        assert result[0].speaker.label == "Speaker B"
        assert result[1].speaker.label == "Speaker B"


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
        # Last segment of chunk 0 should be marked unknown (trailing edge)
        chunk0_segs_in_merged = [s for s in marked if s.chunk_index == 0]
        if chunk0_segs_in_merged:
            assert chunk0_segs_in_merged[-1].speaker.attribution_mode == "unknown"
        # First segment of chunk 1 should be marked unknown (leading edge)
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


# ── Strategy registry tests ───────────────────────────────────────


class TestStrategyRegistry:
    def test_default_strategy_is_heuristic(self):
        strategy = get_strategy()
        assert strategy.strategy_id == STRATEGY_ID

    def test_get_heuristic_by_name(self):
        strategy = get_strategy("pause_heuristic_v1")
        assert strategy.strategy_id == "pause_heuristic_v1"

    def test_get_pyannote_by_name(self):
        strategy = get_strategy("pyannote_v1")
        assert strategy.strategy_id == PYANNOTE_STRATEGY_ID

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown speaker attribution strategy"):
            get_strategy("nonexistent_backend")

    def test_list_strategies_includes_both(self):
        strategies = list_strategies()
        assert "pause_heuristic_v1" in strategies
        assert "pyannote_v1" in strategies

    def test_describe_strategies_returns_all(self):
        descriptions = describe_strategies()
        assert set(descriptions.keys()) == set(list_strategies())
        for sid, desc in descriptions.items():
            assert isinstance(desc, str)
            assert len(desc) > 20  # non-trivial description

    def test_describe_strategies_mentions_requirements(self):
        descriptions = describe_strategies()
        # Pyannote description should mention auth token requirement
        assert "PYANNOTE_AUTH_TOKEN" in descriptions["pyannote_v1"]
        # Heuristic description should indicate no extra dependencies
        assert "no extra dependencies" in descriptions["pause_heuristic_v1"].lower()


# ── Alignment helper tests ────────────────────────────────────────


class TestAlignSegmentsToTurns:
    """Test the overlap-based alignment between segments and speaker turns."""

    def test_perfect_overlap(self):
        """Segment fully inside a single speaker turn → confident."""
        segs = _make_segments([(1.0, 5.0, "hello")])
        turns = [(0.0, 10.0, "SPEAKER_00")]
        label_map = {"SPEAKER_00": "Speaker A"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        assert len(result) == 1
        assert result[0].speaker.label == "Speaker A"
        assert result[0].speaker.attribution_mode == "confident"
        assert result[0].speaker.confidence >= 0.9

    def test_partial_overlap_picks_best(self):
        """Segment spans two turns — picks the one with more overlap."""
        segs = _make_segments([(4.0, 10.0, "crosses boundary")])
        turns = [
            (0.0, 6.0, "SPEAKER_00"),   # overlap: 6-4 = 2s
            (6.0, 12.0, "SPEAKER_01"),   # overlap: 10-6 = 4s
        ]
        label_map = {"SPEAKER_00": "Speaker A", "SPEAKER_01": "Speaker B"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        assert result[0].speaker.label == "Speaker B"

    def test_no_overlap_marks_unknown(self):
        """Segment outside all turns → unknown with low confidence."""
        segs = _make_segments([(20.0, 25.0, "silence region")])
        turns = [(0.0, 10.0, "SPEAKER_00")]
        label_map = {"SPEAKER_00": "Speaker A"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        assert result[0].speaker.label == "Speaker ?"
        assert result[0].speaker.attribution_mode == "unknown"
        assert result[0].speaker.confidence == 0.1

    def test_empty_turns_marks_all_unknown(self):
        """No diarization turns at all → all segments unknown."""
        segs = _make_segments([(0.0, 5.0, "hello")])
        result = _align_segments_to_turns(segs, [], {}, chunk_index=None)
        assert result[0].speaker.attribution_mode == "unknown"

    def test_chunk_index_preserved(self):
        segs = _make_segments([(0.0, 5.0, "hello")])
        turns = [(0.0, 10.0, "SPEAKER_00")]
        label_map = {"SPEAKER_00": "Speaker A"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=2)
        assert result[0].chunk_index == 2

    def test_multiple_speakers_mapped(self):
        """Three segments across two speakers."""
        segs = _make_segments([
            (0.0, 3.0, "A talks"),
            (3.0, 6.0, "B talks"),
            (6.0, 9.0, "A talks again"),
        ])
        turns = [
            (0.0, 3.0, "SPEAKER_00"),
            (3.0, 6.0, "SPEAKER_01"),
            (6.0, 9.0, "SPEAKER_00"),
        ]
        label_map = {"SPEAKER_00": "Speaker A", "SPEAKER_01": "Speaker B"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        labels = [s.speaker.label for s in result]
        assert labels == ["Speaker A", "Speaker B", "Speaker A"]

    def test_low_overlap_ratio_marks_predicted(self):
        """When overlap ratio <= 0.5 (but >= MIN_OVERLAP_RATIO), mode should be 'predicted'."""
        # Segment is 10s, but only 3s overlap with the turn = 0.3 ratio
        segs = _make_segments([(0.0, 10.0, "partially covered")])
        turns = [(7.0, 10.0, "SPEAKER_00")]  # only 3s overlap out of 10s = 0.3
        label_map = {"SPEAKER_00": "Speaker A"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        assert result[0].speaker.attribution_mode == "predicted"
        assert result[0].speaker.confidence < 0.9

    def test_very_low_overlap_marks_unknown(self):
        """When overlap ratio < MIN_OVERLAP_RATIO, mode should be 'unknown'."""
        # Segment is 20s, but only 2s overlap = 0.1 ratio (below 0.15 threshold)
        segs = _make_segments([(0.0, 20.0, "barely covered")])
        turns = [(18.0, 20.0, "SPEAKER_00")]  # 2s overlap out of 20s = 0.1
        label_map = {"SPEAKER_00": "Speaker A"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        assert result[0].speaker.attribution_mode == "unknown"
        assert result[0].speaker.label == "Speaker ?"
        assert result[0].speaker.confidence == 0.1

    def test_overlap_at_threshold_boundary(self):
        """Overlap ratio exactly at MIN_OVERLAP_RATIO is still assigned."""
        # Segment 20s, overlap 3s = 0.15 ratio (exactly at threshold)
        segs = _make_segments([(0.0, 20.0, "at threshold")])
        turns = [(17.0, 20.0, "SPEAKER_00")]
        label_map = {"SPEAKER_00": "Speaker A"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        assert result[0].speaker.label == "Speaker A"
        assert result[0].speaker.attribution_mode == "predicted"

    def test_ambiguous_two_turns_near_equal_overlap(self):
        """When top-two turns have near-equal overlap, assignment is downgraded."""
        # Segment 10s crossing a turn boundary exactly in the middle
        segs = _make_segments([(5.0, 15.0, "crosses boundary evenly")])
        turns = [
            (0.0, 10.0, "SPEAKER_00"),   # overlap: 10-5 = 5s
            (10.0, 20.0, "SPEAKER_01"),   # overlap: 15-10 = 5s
        ]
        label_map = {"SPEAKER_00": "Speaker A", "SPEAKER_01": "Speaker B"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        # Both overlaps are equal → ambiguous → forced to "predicted"
        assert result[0].speaker.attribution_mode == "predicted"
        # Confidence should be capped
        assert result[0].speaker.confidence <= 0.65

    def test_ambiguous_near_equal_still_picks_best(self):
        """Ambiguous assignment still uses the turn with slightly more overlap."""
        # Segment 10s: 4.5s with A, 5.5s with B → difference/best = 1/5.5 ≈ 0.18 < 0.20
        segs = _make_segments([(5.0, 15.0, "slightly biased")])
        turns = [
            (0.0, 9.5, "SPEAKER_00"),    # overlap: 9.5-5 = 4.5s
            (9.5, 20.0, "SPEAKER_01"),    # overlap: 15-9.5 = 5.5s
        ]
        label_map = {"SPEAKER_00": "Speaker A", "SPEAKER_01": "Speaker B"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        # Picks Speaker B (more overlap) but still ambiguous
        assert result[0].speaker.label == "Speaker B"
        assert result[0].speaker.attribution_mode == "predicted"
        assert result[0].speaker.confidence <= 0.65

    def test_not_ambiguous_clear_winner(self):
        """When one turn clearly dominates, assignment is not ambiguous."""
        # Segment 10s: 8s with A, 2s with B → difference/best = 6/8 = 0.75 >> 0.20
        segs = _make_segments([(0.0, 10.0, "clear winner")])
        turns = [
            (0.0, 8.0, "SPEAKER_00"),    # overlap: 8s
            (8.0, 12.0, "SPEAKER_01"),   # overlap: 2s
        ]
        label_map = {"SPEAKER_00": "Speaker A", "SPEAKER_01": "Speaker B"}
        result = _align_segments_to_turns(segs, turns, label_map, chunk_index=None)
        assert result[0].speaker.label == "Speaker A"
        assert result[0].speaker.attribution_mode == "confident"  # 8/10 = 0.8 > 0.5
        assert result[0].speaker.confidence > 0.65


# ── Pyannote strategy tests (mocked) ─────────────────────────────


class TestPyannoteStrategy:
    """Test PyannoteStrategy with mocked pyannote pipeline."""

    def _make_mock_diarization(self, turns):
        """Create a mock diarization result from (start, end, label) triples."""
        mock_diarization = MagicMock()
        track_items = []
        for start, end, label in turns:
            turn = MagicMock()
            turn.start = start
            turn.end = end
            track_items.append((turn, None, label))
        mock_diarization.itertracks.return_value = track_items
        return mock_diarization

    def test_empty_segments_returns_empty(self):
        strategy = PyannoteStrategy(auth_token="fake-token")
        result = strategy.attribute([])
        assert result.segments == []
        assert result.speaker_count == 0
        assert result.strategy_id == "pyannote_v1"

    def test_requires_audio_file(self):
        strategy = PyannoteStrategy(auth_token="fake-token")
        segs = _make_segments([(0.0, 5.0, "hello")])
        with pytest.raises(ValueError, match="requires an audio_file"):
            strategy.attribute(segs)

    def test_missing_pyannote_raises_runtime_error(self):
        strategy = PyannoteStrategy(auth_token="fake-token")
        segs = _make_segments([(0.0, 5.0, "hello")])
        with patch.dict("sys.modules", {"pyannote": None, "pyannote.audio": None}):
            with pytest.raises(RuntimeError, match="pyannote.audio is required"):
                strategy.attribute(segs, audio_file="/tmp/test.wav")

    def test_missing_token_raises_runtime_error(self):
        strategy = PyannoteStrategy(auth_token=None)
        strategy._auth_token = None  # ensure no token
        segs = _make_segments([(0.0, 5.0, "hello")])
        # Mock successful import but no token
        mock_pipeline_cls = MagicMock()
        with patch.dict("sys.modules", {
            "pyannote": MagicMock(),
            "pyannote.audio": MagicMock(Pipeline=mock_pipeline_cls),
        }):
            with pytest.raises(RuntimeError, match="auth token is required"):
                strategy.attribute(segs, audio_file="/tmp/test.wav")

    def test_diarization_with_mocked_pipeline(self):
        """Full flow: mocked pipeline → alignment → AttributionResult."""
        mock_diarization = self._make_mock_diarization([
            (0.0, 5.0, "SPEAKER_00"),
            (5.0, 12.0, "SPEAKER_01"),
        ])
        mock_pipeline = MagicMock(return_value=mock_diarization)

        strategy = PyannoteStrategy(auth_token="fake-token")
        strategy._pipeline = mock_pipeline  # skip lazy loading

        segs = _make_segments([
            (0.0, 4.0, "First speaker here"),
            (5.0, 10.0, "Second speaker now"),
        ])

        result = strategy.attribute(segs, audio_file="/tmp/test.wav")

        assert isinstance(result, AttributionResult)
        assert result.strategy_id == "pyannote_v1"
        assert result.speaker_count == 2
        assert len(result.segments) == 2
        assert result.segments[0].speaker.label == "Speaker A"
        assert result.segments[1].speaker.label == "Speaker B"
        assert result.metadata["model"] == "pyannote/speaker-diarization-3.1"
        assert result.metadata["diarization_turns"] == 2

        mock_pipeline.assert_called_once_with("/tmp/test.wav")

    def test_attribution_modes(self):
        """High-overlap → confident, low-overlap → predicted."""
        mock_diarization = self._make_mock_diarization([
            (0.0, 10.0, "SPEAKER_00"),  # covers seg0 fully, seg1 partially
        ])
        mock_pipeline = MagicMock(return_value=mock_diarization)

        strategy = PyannoteStrategy(auth_token="fake-token")
        strategy._pipeline = mock_pipeline

        segs = _make_segments([
            (1.0, 5.0, "fully inside"),       # 100% overlap → confident
            (8.0, 20.0, "mostly outside"),     # 2/12 = 16.7% overlap → predicted
        ])

        result = strategy.attribute(segs, audio_file="/tmp/test.wav")
        assert result.segments[0].speaker.attribution_mode == "confident"
        assert result.segments[1].speaker.attribution_mode == "predicted"

    def test_chunk_index_threaded(self):
        """chunk_index parameter is passed to output segments."""
        mock_diarization = self._make_mock_diarization([
            (0.0, 10.0, "SPEAKER_00"),
        ])
        mock_pipeline = MagicMock(return_value=mock_diarization)

        strategy = PyannoteStrategy(auth_token="fake-token")
        strategy._pipeline = mock_pipeline

        segs = _make_segments([(0.0, 5.0, "hello")])
        result = strategy.attribute(segs, chunk_index=3, audio_file="/tmp/test.wav")
        assert result.segments[0].chunk_index == 3

    def test_deterministic_label_ordering(self):
        """Speaker labels are assigned in sorted order of pyannote labels."""
        mock_diarization = self._make_mock_diarization([
            (0.0, 5.0, "SPEAKER_02"),
            (5.0, 10.0, "SPEAKER_00"),
            (10.0, 15.0, "SPEAKER_01"),
        ])
        mock_pipeline = MagicMock(return_value=mock_diarization)

        strategy = PyannoteStrategy(auth_token="fake-token")
        strategy._pipeline = mock_pipeline

        segs = _make_segments([
            (0.0, 5.0, "first"),
            (5.0, 10.0, "second"),
            (10.0, 15.0, "third"),
        ])
        result = strategy.attribute(segs, audio_file="/tmp/test.wav")
        # Sorted order: SPEAKER_00→A, SPEAKER_01→B, SPEAKER_02→C
        labels = [s.speaker.label for s in result.segments]
        assert labels == ["Speaker C", "Speaker A", "Speaker B"]
