"""Job lifecycle management service.

In-memory implementation for Unit 1. SQLite persistence
will replace the in-memory store in Unit 2.
"""

from datetime import datetime
from typing import Optional

from src.models.job import Job, JobStatus


class JobService:
    """Manages job creation, lookup, and lifecycle transitions.

    Currently uses in-memory storage. The interface is designed
    so that swapping to SQLite (Unit 2) requires no changes to
    callers.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create_job(
        self,
        url: str,
        language: Optional[str] = None,
        skip_correction: bool = False,
        custom_terms: Optional[list[str]] = None,
    ) -> Job:
        """Create a new transcription job."""
        job_id = f"job_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        job = Job(
            job_id=job_id,
            url=url,
            language=language,
            skip_correction=skip_correction,
            custom_terms=custom_terms,
            message="任務已建立，等待處理...",
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Look up a job by ID. Returns None if not found."""
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: JobStatus,
        progress: int,
        message: str = "",
    ) -> None:
        """Update a job's lifecycle state."""
        job = self._jobs.get(job_id)
        if job:
            job.update(status, progress, message)

    def complete_job(self, job_id: str) -> None:
        """Mark a job as completed."""
        job = self._jobs.get(job_id)
        if job:
            job.complete()

    def fail_job(self, job_id: str, error: str) -> None:
        """Mark a job as failed."""
        job = self._jobs.get(job_id)
        if job:
            job.fail(error)
