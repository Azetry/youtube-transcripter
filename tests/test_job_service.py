"""Tests for JobService."""

from src.services.job_service import JobService
from src.models.job import JobStatus


def test_create_job():
    svc = JobService()
    job = svc.create_job(url="https://youtube.com/watch?v=abc", language="zh")
    assert job.url == "https://youtube.com/watch?v=abc"
    assert job.language == "zh"
    assert job.status == JobStatus.PENDING
    assert job.job_id.startswith("job_")


def test_get_job():
    svc = JobService()
    job = svc.create_job(url="https://youtube.com/watch?v=abc")
    found = svc.get_job(job.job_id)
    assert found is not None
    assert found.job_id == job.job_id


def test_get_job_not_found():
    svc = JobService()
    assert svc.get_job("nonexistent") is None


def test_update_job():
    svc = JobService()
    job = svc.create_job(url="https://youtube.com/watch?v=abc")
    svc.update_job(job.job_id, JobStatus.TRANSCRIBING, 50, "halfway")
    found = svc.get_job(job.job_id)
    assert found.status == JobStatus.TRANSCRIBING
    assert found.progress == 50


def test_complete_job():
    svc = JobService()
    job = svc.create_job(url="https://youtube.com/watch?v=abc")
    svc.complete_job(job.job_id)
    found = svc.get_job(job.job_id)
    assert found.status == JobStatus.COMPLETED
    assert found.progress == 100


def test_fail_job():
    svc = JobService()
    job = svc.create_job(url="https://youtube.com/watch?v=abc")
    svc.fail_job(job.job_id, "timeout")
    found = svc.get_job(job.job_id)
    assert found.status == JobStatus.FAILED
    assert found.error == "timeout"


def test_multiple_jobs_isolated():
    svc = JobService()
    j1 = svc.create_job(url="https://youtube.com/watch?v=a")
    j2 = svc.create_job(url="https://youtube.com/watch?v=b")
    svc.complete_job(j1.job_id)
    assert svc.get_job(j1.job_id).status == JobStatus.COMPLETED
    assert svc.get_job(j2.job_id).status == JobStatus.PENDING
