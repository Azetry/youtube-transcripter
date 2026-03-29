"""Tests for speaker attribution acceptance visibility in CLI artifacts."""

import json
import os
import tempfile

from src.models.transcript import TranscriptArtifacts
from src.youtube_extractor import VideoInfo

# Reusable fixture data
_VIDEO_INFO = VideoInfo(
    video_id="test123",
    title="Test Video",
    description="desc",
    duration=120,
    upload_date="2026-01-01",
    channel="TestCh",
    channel_id="UC123",
    view_count=100,
    thumbnail_url="https://example.com/thumb.jpg",
)

_SPEAKER_SEGMENTS = [
    {
        "start": 0.0,
        "end": 5.0,
        "text": "Hello world",
        "speaker": {"label": "Speaker A", "confidence": 0.5, "attribution_mode": "predicted"},
    },
    {
        "start": 8.0,
        "end": 12.0,
        "text": "Hi there",
        "speaker": {"label": "Speaker B", "confidence": 0.4, "attribution_mode": "predicted"},
    },
]


def _make_artifacts(speaker_enabled=False, strategy="", count=0, segments=None):
    return TranscriptArtifacts(
        video_info=_VIDEO_INFO,
        original_text="original",
        corrected_text="corrected",
        language="en",
        speaker_attribution_enabled=speaker_enabled,
        speaker_strategy=strategy,
        speaker_count=count,
        speaker_segments=segments,
    )


class TestMetadataSpeakerFields:
    """Saved _metadata.json must include speaker attribution when enabled."""

    def _save_and_load_metadata(self, artifacts):
        from main import save_transcript

        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_transcript(
                _VIDEO_INFO, "original", "corrected",
                output_dir=tmpdir, artifacts=artifacts,
            )
            with open(saved["metadata"], encoding="utf-8") as f:
                return saved, json.load(f)

    def test_metadata_includes_speaker_attribution_when_enabled(self):
        artifacts = _make_artifacts(
            speaker_enabled=True,
            strategy="pause_heuristic_v1",
            count=2,
            segments=_SPEAKER_SEGMENTS,
        )
        saved, meta = self._save_and_load_metadata(artifacts)

        assert "speaker_attribution" in meta
        sa = meta["speaker_attribution"]
        assert sa["enabled"] is True
        assert sa["strategy"] == "pause_heuristic_v1"
        assert sa["detected_speaker_count"] == 2
        assert sa["speaker_segments_file"] is not None

    def test_metadata_omits_speaker_attribution_when_disabled(self):
        artifacts = _make_artifacts(speaker_enabled=False)
        _, meta = self._save_and_load_metadata(artifacts)
        assert "speaker_attribution" not in meta

    def test_metadata_omits_speaker_attribution_without_artifacts(self):
        from main import save_transcript

        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_transcript(
                _VIDEO_INFO, "original", "corrected", output_dir=tmpdir,
            )
            with open(saved["metadata"], encoding="utf-8") as f:
                meta = json.load(f)
        assert "speaker_attribution" not in meta

    def test_segments_file_pointer_null_when_no_segments(self):
        artifacts = _make_artifacts(
            speaker_enabled=True, strategy="pause_heuristic_v1", count=0,
            segments=None,
        )
        _, meta = self._save_and_load_metadata(artifacts)
        assert meta["speaker_attribution"]["speaker_segments_file"] is None


class TestSpeakerSegmentsFile:
    """Speaker segments saved as separate JSON file."""

    def test_speaker_segments_file_created(self):
        from main import save_transcript

        artifacts = _make_artifacts(
            speaker_enabled=True, strategy="pause_heuristic_v1",
            count=2, segments=_SPEAKER_SEGMENTS,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_transcript(
                _VIDEO_INFO, "original", "corrected",
                output_dir=tmpdir, artifacts=artifacts,
            )
            assert "speaker_segments" in saved
            assert os.path.exists(saved["speaker_segments"])

            with open(saved["speaker_segments"], encoding="utf-8") as f:
                segments = json.load(f)
            assert len(segments) == 2
            assert segments[0]["speaker"]["label"] == "Speaker A"

    def test_no_segments_file_when_disabled(self):
        from main import save_transcript

        artifacts = _make_artifacts(speaker_enabled=False)
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_transcript(
                _VIDEO_INFO, "original", "corrected",
                output_dir=tmpdir, artifacts=artifacts,
            )
            assert "speaker_segments" not in saved


class TestSpeakerAttributionSummaryFormat:
    """format_speaker_attribution_summary matches process_video panel body."""

    def test_includes_strategy_count_and_segments_path(self):
        from main import format_speaker_attribution_summary

        artifacts = _make_artifacts(
            speaker_enabled=True,
            strategy="pause_heuristic_v1",
            count=2,
            segments=_SPEAKER_SEGMENTS,
        )
        text = format_speaker_attribution_summary(
            artifacts,
            {"speaker_segments": "/tmp/fake_segments.json"},
        )
        assert text is not None
        assert "Strategy: pause_heuristic_v1" in text
        assert "Detected speakers: 2" in text
        assert "Segments file: /tmp/fake_segments.json" in text

    def test_omits_segments_line_when_not_in_saved_files(self):
        from main import format_speaker_attribution_summary

        artifacts = _make_artifacts(
            speaker_enabled=True,
            strategy="pause_heuristic_v1",
            count=2,
            segments=_SPEAKER_SEGMENTS,
        )
        text = format_speaker_attribution_summary(artifacts, {})
        assert text is not None
        assert "Segments file:" not in text

    def test_returns_none_when_disabled(self):
        from main import format_speaker_attribution_summary

        artifacts = _make_artifacts(speaker_enabled=False)
        assert format_speaker_attribution_summary(artifacts, {}) is None


class TestMetadataSegmentsFileConsistency:
    """The pointer in metadata should match the actual segments file path."""

    def test_metadata_pointer_matches_segments_path(self):
        from main import save_transcript

        artifacts = _make_artifacts(
            speaker_enabled=True, strategy="pyannote_v1",
            count=3, segments=_SPEAKER_SEGMENTS,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_transcript(
                _VIDEO_INFO, "original", "corrected",
                output_dir=tmpdir, artifacts=artifacts,
            )
            with open(saved["metadata"], encoding="utf-8") as f:
                meta = json.load(f)

            pointer = meta["speaker_attribution"]["speaker_segments_file"]
            assert pointer == saved["speaker_segments"]
            assert os.path.exists(pointer)
