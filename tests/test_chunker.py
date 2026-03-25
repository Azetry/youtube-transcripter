"""Tests for deterministic audio chunking (Unit C - Task 3.1).

Covers chunk plan generation, edge cases, and the needs_chunking helper.
"""

import os
import tempfile

import pytest

from src.media.chunker import (
    ChunkPlan,
    plan_chunks,
    needs_chunking,
    generate_chunk_files,
    DEFAULT_CHUNK_DURATION,
    DEFAULT_OVERLAP,
)


class TestPlanChunks:
    """Deterministic chunk planning from audio duration."""

    def test_short_audio_single_chunk(self):
        """Audio shorter than chunk_duration produces one chunk."""
        plans = plan_chunks(300.0)  # 5 minutes
        assert len(plans) == 1
        assert plans[0].index == 0
        assert plans[0].start_time == 0.0
        assert plans[0].end_time == 300.0
        assert plans[0].duration == 300.0
        assert plans[0].is_last is True

    def test_exact_chunk_duration_single_chunk(self):
        """Audio exactly equal to chunk_duration is a single chunk."""
        plans = plan_chunks(600.0)
        assert len(plans) == 1
        assert plans[0].end_time == 600.0

    def test_two_chunks_with_overlap(self):
        """Audio just over one chunk produces two chunks with overlap."""
        # 610 seconds = 10 min 10 sec
        plans = plan_chunks(610.0)
        assert len(plans) == 2

        # First chunk: 0 to 600
        assert plans[0].index == 0
        assert plans[0].start_time == 0.0
        assert plans[0].end_time == 600.0
        assert plans[0].is_last is False

        # Second chunk starts at 600 - 15 = 585
        assert plans[1].index == 1
        assert plans[1].start_time == 585.0
        assert plans[1].end_time == 610.0
        assert plans[1].is_last is True

    def test_three_chunks(self):
        """Audio spanning three chunks."""
        # 1200 seconds = 20 minutes exactly
        # step = 600 - 15 = 585
        # chunk 0: 0-600, chunk 1: 585-1185, chunk 2: 1170-1200
        plans = plan_chunks(1200.0)
        assert len(plans) == 3
        assert plans[0].start_time == 0.0
        assert plans[0].end_time == 600.0
        assert plans[1].start_time == 585.0
        assert plans[1].end_time == 1185.0
        assert plans[2].start_time == 1170.0
        assert plans[2].end_time == 1200.0
        assert plans[2].is_last is True

    def test_short_final_chunk_merged(self):
        """A degenerate short final chunk (< overlap) is merged into previous."""
        # step = 585, so after first chunk ends at 600, next starts at 585
        # Total 605: chunk 0 starts at 0, end would be 600, remaining = 5 < 15
        # So chunk 0 extends to 605
        plans = plan_chunks(605.0)
        assert len(plans) == 1
        assert plans[0].end_time == 605.0
        assert plans[0].is_last is True

    def test_exact_boundary_alignment(self):
        """Audio that aligns exactly at chunk + step boundaries."""
        # 1185 = 600 + 585
        plans = plan_chunks(1185.0)
        assert len(plans) == 2
        assert plans[0].end_time == 600.0
        assert plans[1].start_time == 585.0
        assert plans[1].end_time == 1185.0

    def test_deterministic(self):
        """Same inputs always produce same plan."""
        plans1 = plan_chunks(3600.0)
        plans2 = plan_chunks(3600.0)
        assert len(plans1) == len(plans2)
        for p1, p2 in zip(plans1, plans2):
            assert p1 == p2

    def test_full_coverage(self):
        """Every second of audio is covered by at least one chunk."""
        total = 1800.0  # 30 minutes
        plans = plan_chunks(total)
        # First chunk starts at 0
        assert plans[0].start_time == 0.0
        # Last chunk ends at total
        assert plans[-1].end_time == total
        # Adjacent chunks overlap (no gap)
        for i in range(len(plans) - 1):
            assert plans[i + 1].start_time < plans[i].end_time

    def test_overlap_region_exists(self):
        """Adjacent chunks share an overlap region of at least `overlap` seconds."""
        plans = plan_chunks(1200.0)
        for i in range(len(plans) - 1):
            overlap_size = plans[i].end_time - plans[i + 1].start_time
            assert overlap_size >= DEFAULT_OVERLAP

    def test_custom_chunk_duration_and_overlap(self):
        """Custom policy: 5-minute chunks with 10-second overlap."""
        plans = plan_chunks(610.0, chunk_duration=300, overlap=10)
        assert len(plans) == 3
        assert plans[0].end_time == 300.0
        # step = 300 - 10 = 290
        assert plans[1].start_time == 290.0

    def test_invalid_duration_raises(self):
        with pytest.raises(ValueError, match="positive"):
            plan_chunks(0)

    def test_invalid_negative_duration_raises(self):
        with pytest.raises(ValueError, match="positive"):
            plan_chunks(-10)

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError, match="less than"):
            plan_chunks(1200.0, chunk_duration=600, overlap=600)

    def test_zero_overlap_allowed(self):
        """Overlap of zero should produce non-overlapping chunks."""
        plans = plan_chunks(1200.0, chunk_duration=600, overlap=0)
        assert len(plans) == 2
        assert plans[0].end_time == 600.0
        assert plans[1].start_time == 600.0

    def test_chunk_plan_is_frozen(self):
        """ChunkPlan is immutable (frozen dataclass)."""
        plan = plan_chunks(300.0)[0]
        with pytest.raises(AttributeError):
            plan.start_time = 99.0


class TestNeedsChunking:
    def test_short_video_no_chunking(self):
        assert needs_chunking(300.0) is False

    def test_exact_boundary_no_chunking(self):
        assert needs_chunking(600.0) is False

    def test_long_video_needs_chunking(self):
        assert needs_chunking(601.0) is True

    def test_custom_threshold(self):
        assert needs_chunking(301.0, chunk_duration=300) is True
        assert needs_chunking(300.0, chunk_duration=300) is False


class TestGenerateChunkFiles:
    def test_single_chunk_returns_original(self, tmp_path):
        """Short audio returns original file path without ffmpeg."""
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio data")
        artifacts = generate_chunk_files(
            str(audio), 300.0, str(tmp_path / "chunks"), "job1"
        )
        assert len(artifacts) == 1
        assert artifacts[0].file_path == str(audio)
        assert artifacts[0].index == 0

    def test_missing_audio_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            generate_chunk_files(
                str(tmp_path / "nonexistent.mp3"),
                1200.0,
                str(tmp_path / "chunks"),
                "job1",
            )

    def test_output_dir_created(self, tmp_path):
        """Output directory is created if it doesn't exist."""
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake")
        out_dir = str(tmp_path / "deep" / "chunks")
        # Will fail at ffmpeg but dir should be created
        try:
            generate_chunk_files(str(audio), 1200.0, out_dir, "job1")
        except RuntimeError:
            pass
        assert os.path.isdir(out_dir)
