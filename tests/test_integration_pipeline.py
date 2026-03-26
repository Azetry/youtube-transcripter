"""Integration tests for the end-to-end transcription pipeline.

These tests mock external APIs (YouTube download, Whisper, GPT) but exercise
the full service-layer orchestration for both short-video and long-video paths.
"""

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from src.media.chunker import DEFAULT_CHUNK_DURATION
from src.models.job import JobStatus
from src.models.transcript import TranscriptArtifacts
from src.services.job_service import JobService
from src.services.transcription_service import AcquisitionOutcome, TranscriptionService
from src.storage.schema import bootstrap
from src.storage.sqlite_store import SQLiteStore
from src.youtube_extractor import VideoInfo


# ── Fixtures ─────────────────────────────────────────────────────────

def _make_video_info(duration: int, audio_file: str) -> VideoInfo:
    return VideoInfo(
        video_id="test123",
        title="Test Video",
        description="A test video",
        duration=duration,
        upload_date="20240101",
        channel="TestChannel",
        channel_id="UC_test",
        view_count=1000,
        thumbnail_url="https://example.com/thumb.jpg",
        audio_file=audio_file,
    )


@pytest.fixture
def tmp_dirs():
    with tempfile.TemporaryDirectory() as d:
        dl = os.path.join(d, "downloads")
        out = os.path.join(d, "transcripts")
        os.makedirs(dl)
        os.makedirs(out)
        yield dl, out


@pytest.fixture
def sqlite_store():
    conn = bootstrap(":memory:")
    store = SQLiteStore(conn)
    yield store
    conn.close()


# ── Short-video integration test ─────────────────────────────────────


class TestShortVideoPipeline:
    """Short video (≤10 min): single-pass transcribe → correct → diff."""

    def test_short_video_end_to_end(self, tmp_dirs):
        dl_dir, out_dir = tmp_dirs

        # Create a dummy audio file
        audio_path = os.path.join(dl_dir, "test_audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        short_duration = 300  # 5 minutes
        video_info = _make_video_info(short_duration, audio_path)

        svc = TranscriptionService(download_dir=dl_dir, output_dir=out_dir)

        # Mock external services
        mock_transcript = MagicMock()
        mock_transcript.text = "This is the raw transcript text."
        mock_transcript.language = "en"
        mock_transcript.duration = short_duration

        progress_calls = []

        with patch.object(svc, "_acquire", return_value=AcquisitionOutcome(video_info=video_info, success=True)), \
             patch.object(svc.transcriber, "transcribe", return_value=mock_transcript), \
             patch.object(svc.corrector, "correct", return_value="This is the corrected transcript text."):

            result = svc.run(
                url="https://www.youtube.com/watch?v=test123",
                language="en",
                on_progress=lambda s, p, m: progress_calls.append((s, p, m)),
            )

        assert isinstance(result, TranscriptArtifacts)
        assert result.original_text == "This is the raw transcript text."
        assert result.corrected_text == "This is the corrected transcript text."
        assert result.language == "en"
        assert result.video_info.video_id == "test123"
        assert result.is_merged is False
        assert result.chunk_count == 0
        assert result.similarity_ratio > 0  # diff was computed
        assert len(progress_calls) >= 3  # download, transcribe, correct/diff stages

    def test_short_video_skip_correction(self, tmp_dirs):
        dl_dir, out_dir = tmp_dirs
        audio_path = os.path.join(dl_dir, "test_audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        video_info = _make_video_info(200, audio_path)
        svc = TranscriptionService(download_dir=dl_dir, output_dir=out_dir)

        mock_transcript = MagicMock()
        mock_transcript.text = "Raw text here."
        mock_transcript.language = "zh"
        mock_transcript.duration = 200

        with patch.object(svc, "_acquire", return_value=AcquisitionOutcome(video_info=video_info, success=True)), \
             patch.object(svc.transcriber, "transcribe", return_value=mock_transcript) as mock_t, \
             patch.object(svc.corrector, "correct") as mock_c:

            result = svc.run(
                url="https://www.youtube.com/watch?v=test123",
                skip_correction=True,
            )

        assert result.original_text == result.corrected_text == "Raw text here."
        mock_c.assert_not_called()

    def test_short_video_with_custom_terms(self, tmp_dirs):
        dl_dir, out_dir = tmp_dirs
        audio_path = os.path.join(dl_dir, "test_audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        video_info = _make_video_info(200, audio_path)
        svc = TranscriptionService(download_dir=dl_dir, output_dir=out_dir)

        mock_transcript = MagicMock()
        mock_transcript.text = "Raw text."
        mock_transcript.language = "en"
        mock_transcript.duration = 200

        with patch.object(svc, "_acquire", return_value=AcquisitionOutcome(video_info=video_info, success=True)), \
             patch.object(svc.transcriber, "transcribe", return_value=mock_transcript), \
             patch.object(svc.corrector, "correct_with_terms", return_value="Corrected.") as mock_ct:

            result = svc.run(
                url="https://www.youtube.com/watch?v=test123",
                custom_terms=["OpenAI", "GPT"],
            )

        mock_ct.assert_called_once()
        assert result.corrected_text == "Corrected."


# ── Long-video integration test ──────────────────────────────────────


class TestLongVideoPipeline:
    """Long video (>10 min): chunk → transcribe each → correct each → merge → diff."""

    def _make_whisper_response(self, text: str, segments: list[dict], lang: str = "en"):
        """Build a mock transcribe_with_timestamps return value."""
        return {
            "text": text,
            "language": lang,
            "duration": 600.0,
            "segments": segments,
        }

    def test_long_video_end_to_end(self, tmp_dirs):
        dl_dir, out_dir = tmp_dirs

        # Create a dummy audio file
        audio_path = os.path.join(dl_dir, "long_audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        long_duration = 1300  # ~21 minutes → should produce 3 chunks
        video_info = _make_video_info(long_duration, audio_path)

        svc = TranscriptionService(download_dir=dl_dir, output_dir=out_dir)

        # Build per-chunk mock responses
        chunk_responses = [
            self._make_whisper_response(
                "First chunk transcript. This is the beginning.",
                [
                    {"start": 0.0, "end": 5.0, "text": "First chunk transcript."},
                    {"start": 5.0, "end": 10.0, "text": "This is the beginning."},
                ],
            ),
            self._make_whisper_response(
                "Second chunk transcript. Middle section here.",
                [
                    {"start": 0.0, "end": 5.0, "text": "Second chunk transcript."},
                    {"start": 5.0, "end": 10.0, "text": "Middle section here."},
                ],
            ),
            self._make_whisper_response(
                "Third chunk transcript. This is the end.",
                [
                    {"start": 0.0, "end": 5.0, "text": "Third chunk transcript."},
                    {"start": 5.0, "end": 10.0, "text": "This is the end."},
                ],
            ),
        ]

        call_count = {"n": 0}

        def mock_transcribe_with_timestamps(audio_file, language=None, prompt=None):
            idx = call_count["n"]
            call_count["n"] += 1
            return chunk_responses[min(idx, len(chunk_responses) - 1)]

        corrected_texts = [
            "First chunk corrected. This is the beginning.",
            "Second chunk corrected. Middle section here.",
            "Third chunk corrected. This is the end.",
        ]
        correct_count = {"n": 0}

        def mock_correct(text, context=None):
            idx = correct_count["n"]
            correct_count["n"] += 1
            return corrected_texts[min(idx, len(corrected_texts) - 1)]

        # Mock generate_chunk_files to avoid ffmpeg dependency
        from src.media.chunker import ChunkArtifact

        def mock_generate_chunks(audio_file, total_duration, output_dir, job_id, **kw):
            # Simulate 3 chunks with overlap
            artifacts = []
            for i, (start, end) in enumerate([(0, 600), (585, 1185), (1170, 1300)]):
                chunk_path = os.path.join(output_dir, f"{job_id}_chunk_{i:03d}.mp3")
                with open(chunk_path, "wb") as f:
                    f.write(b"\x00" * 50)
                artifacts.append(ChunkArtifact(
                    index=i, start_time=start, end_time=end, file_path=chunk_path,
                ))
            return artifacts

        progress_calls = []

        with patch.object(svc, "_acquire", return_value=AcquisitionOutcome(video_info=video_info, success=True)), \
             patch("src.services.transcription_service.generate_chunk_files", mock_generate_chunks), \
             patch.object(svc.transcriber, "transcribe_with_timestamps", side_effect=mock_transcribe_with_timestamps), \
             patch.object(svc.corrector, "correct", side_effect=mock_correct):

            result = svc.run(
                url="https://www.youtube.com/watch?v=longvideo",
                language="en",
                job_id="job_test_long",
                on_progress=lambda s, p, m: progress_calls.append((s, p, m)),
            )

        # Verify long-video artifacts
        assert isinstance(result, TranscriptArtifacts)
        assert result.is_merged is True
        assert result.chunk_count == 3
        assert result.segments_before_dedup > 0
        assert result.segments_after_dedup > 0
        assert result.consistency_text  # non-empty
        assert result.language == "en"
        assert result.video_info.video_id == "test123"

        # Diff should have been computed
        assert result.diff_inline is not None

        # Original text is merged raw, corrected text is consistency-passed
        assert result.original_text  # non-empty merged raw
        assert result.corrected_text  # non-empty final corrected

        # Progress should include MERGING status
        statuses = [s for s, p, m in progress_calls]
        assert JobStatus.MERGING in statuses
        assert JobStatus.TRANSCRIBING in statuses

    def test_long_video_skip_correction(self, tmp_dirs):
        dl_dir, out_dir = tmp_dirs
        audio_path = os.path.join(dl_dir, "long_audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        video_info = _make_video_info(1300, audio_path)
        svc = TranscriptionService(download_dir=dl_dir, output_dir=out_dir)

        def mock_transcribe_ts(audio_file, language=None, prompt=None):
            return {
                "text": "Chunk text.",
                "language": "en",
                "duration": 600.0,
                "segments": [{"start": 0.0, "end": 5.0, "text": "Chunk text."}],
            }

        from src.media.chunker import ChunkArtifact

        def mock_gen_chunks(audio_file, total_duration, output_dir, job_id, **kw):
            artifacts = []
            for i, (s, e) in enumerate([(0, 600), (585, 1185), (1170, 1300)]):
                p = os.path.join(output_dir, f"{job_id}_chunk_{i:03d}.mp3")
                with open(p, "wb") as f:
                    f.write(b"\x00" * 50)
                artifacts.append(ChunkArtifact(index=i, start_time=s, end_time=e, file_path=p))
            return artifacts

        with patch.object(svc, "_acquire", return_value=AcquisitionOutcome(video_info=video_info, success=True)), \
             patch("src.services.transcription_service.generate_chunk_files", mock_gen_chunks), \
             patch.object(svc.transcriber, "transcribe_with_timestamps", side_effect=mock_transcribe_ts), \
             patch.object(svc.corrector, "correct") as mock_c:

            result = svc.run(
                url="https://www.youtube.com/watch?v=longvid",
                skip_correction=True,
                job_id="job_skip",
            )

        mock_c.assert_not_called()
        assert result.is_merged is True
        # raw and corrected are the same when skipping correction
        assert result.original_text == result.corrected_text


# ── Job persistence integration ──────────────────────────────────────


class TestJobPersistenceIntegration:
    """Verify job + result + merge fields persist correctly through the pipeline."""

    def test_store_and_retrieve_merged_result(self, sqlite_store):
        job_svc = JobService(store=sqlite_store)

        # Create a job
        job = job_svc.create_job(url="https://www.youtube.com/watch?v=test")

        # Store base result
        result_data = {
            "video_id": "test",
            "title": "Test",
            "channel": "Ch",
            "duration": 1300,
            "original_text": "raw merged text",
            "corrected_text": "corrected merged text",
            "language": "en",
            "similarity_ratio": 0.95,
            "change_count": 5,
            "diff_inline": "[+corrected+]",
            "processed_at": "2024-01-01T00:00:00",
        }
        job_svc.store_result(job.job_id, result_data)

        # Store merge fields
        job_svc.store_merge_fields(job.job_id, {
            "is_merged": 1,
            "chunk_count": 3,
            "segments_before_dedup": 12,
            "segments_after_dedup": 10,
            "consistency_text": "final consistency text",
        })

        # Retrieve and verify
        stored = job_svc.get_result(job.job_id)
        assert stored is not None
        assert stored["is_merged"] == 1
        assert stored["chunk_count"] == 3
        assert stored["segments_before_dedup"] == 12
        assert stored["segments_after_dedup"] == 10
        assert stored["consistency_text"] == "final consistency text"
        assert stored["original_text"] == "raw merged text"

    def test_non_merged_result_has_null_merge_fields(self, sqlite_store):
        job_svc = JobService(store=sqlite_store)
        job = job_svc.create_job(url="https://www.youtube.com/watch?v=short")

        result_data = {
            "video_id": "short",
            "title": "Short",
            "channel": "Ch",
            "duration": 300,
            "original_text": "text",
            "corrected_text": "text",
            "language": "en",
            "similarity_ratio": 1.0,
            "change_count": 0,
            "diff_inline": "",
            "processed_at": "2024-01-01T00:00:00",
        }
        job_svc.store_result(job.job_id, result_data)

        stored = job_svc.get_result(job.job_id)
        assert stored["is_merged"] is None or stored["is_merged"] == 0
        assert stored["chunk_count"] == 1

    def test_merging_status_transition(self):
        """Verify MERGING is a valid status transition."""
        job_svc = JobService()
        job = job_svc.create_job(url="https://www.youtube.com/watch?v=test")

        job_svc.update_job(job.job_id, JobStatus.MERGING, 80, "合併中...")
        updated = job_svc.get_job(job.job_id)
        assert updated.status == JobStatus.MERGING
        assert updated.progress == 80


# ── Audio cleanup integration ────────────────────────────────────────


class TestCleanup:
    """Verify audio + chunk files are cleaned up after pipeline."""

    def test_audio_cleaned_up_short_video(self, tmp_dirs):
        dl_dir, out_dir = tmp_dirs
        audio_path = os.path.join(dl_dir, "audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        video_info = _make_video_info(200, audio_path)
        svc = TranscriptionService(download_dir=dl_dir, output_dir=out_dir)

        mock_t = MagicMock()
        mock_t.text = "text"
        mock_t.language = "en"
        mock_t.duration = 200

        with patch.object(svc, "_acquire", return_value=AcquisitionOutcome(video_info=video_info, success=True)), \
             patch.object(svc.transcriber, "transcribe", return_value=mock_t), \
             patch.object(svc.corrector, "correct", return_value="text"):
            svc.run(url="https://www.youtube.com/watch?v=x")

        assert not os.path.exists(audio_path), "Audio file should be cleaned up"

    def test_chunk_files_cleaned_up_long_video(self, tmp_dirs):
        dl_dir, out_dir = tmp_dirs
        audio_path = os.path.join(dl_dir, "audio.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"\x00" * 100)

        video_info = _make_video_info(1300, audio_path)
        svc = TranscriptionService(download_dir=dl_dir, output_dir=out_dir)

        from src.media.chunker import ChunkArtifact
        chunk_paths = []

        def mock_gen(audio_file, total_duration, output_dir, job_id, **kw):
            artifacts = []
            for i in range(2):
                p = os.path.join(output_dir, f"chunk_{i}.mp3")
                with open(p, "wb") as f:
                    f.write(b"\x00" * 50)
                chunk_paths.append(p)
                artifacts.append(ChunkArtifact(index=i, start_time=i*585, end_time=i*585+600, file_path=p))
            return artifacts

        def mock_ts(audio_file, language=None, prompt=None):
            return {
                "text": "text", "language": "en", "duration": 600,
                "segments": [{"start": 0, "end": 5, "text": "text"}],
            }

        with patch.object(svc, "_acquire", return_value=AcquisitionOutcome(video_info=video_info, success=True)), \
             patch("src.services.transcription_service.generate_chunk_files", mock_gen), \
             patch.object(svc.transcriber, "transcribe_with_timestamps", side_effect=mock_ts), \
             patch.object(svc.corrector, "correct", return_value="text"):
            svc.run(url="https://www.youtube.com/watch?v=x", job_id="j1")

        assert not os.path.exists(audio_path), "Audio file should be cleaned up"
        for p in chunk_paths:
            assert not os.path.exists(p), f"Chunk file {p} should be cleaned up"
