"""Tests for canonical models."""

from src.models.job import Job, JobStatus
from src.models.transcript import TranscriptArtifacts
from src.youtube_extractor import VideoInfo


def test_job_creation():
    job = Job(job_id="test_1", url="https://youtube.com/watch?v=abc")
    assert job.status == JobStatus.PENDING
    assert job.progress == 0
    assert job.error is None


def test_job_update():
    job = Job(job_id="test_1", url="https://youtube.com/watch?v=abc")
    job.update(JobStatus.TRANSCRIBING, 40, "Whisper 轉錄中...")
    assert job.status == JobStatus.TRANSCRIBING
    assert job.progress == 40
    assert job.message == "Whisper 轉錄中..."


def test_job_complete():
    job = Job(job_id="test_1", url="https://youtube.com/watch?v=abc")
    job.complete()
    assert job.status == JobStatus.COMPLETED
    assert job.progress == 100
    assert job.completed_at is not None


def test_job_fail():
    job = Job(job_id="test_1", url="https://youtube.com/watch?v=abc")
    job.fail("some error")
    assert job.status == JobStatus.FAILED
    assert job.error == "some error"


def test_job_status_values():
    """Ensure status values match API contract."""
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.DOWNLOADING.value == "downloading"
    assert JobStatus.TRANSCRIBING.value == "transcribing"
    assert JobStatus.CORRECTING.value == "correcting"
    assert JobStatus.COMPLETED.value == "completed"
    assert JobStatus.FAILED.value == "failed"


def test_transcript_artifacts():
    video_info = VideoInfo(
        video_id="abc",
        title="Test",
        description="desc",
        duration=120,
        upload_date="20240101",
        channel="TestChannel",
        channel_id="ch_1",
        view_count=100,
        thumbnail_url="http://example.com/thumb.jpg",
    )
    artifacts = TranscriptArtifacts(
        video_info=video_info,
        original_text="hello",
        corrected_text="Hello.",
        language="en",
    )
    assert artifacts.original_text == "hello"
    assert artifacts.corrected_text == "Hello."
    assert artifacts.similarity_ratio == 0.0  # default
    assert artifacts.saved_files is None
