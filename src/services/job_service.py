"""Job lifecycle management service.

SQLite-backed implementation (Unit 2). Jobs survive process restarts.
Falls back to in-memory storage when no SQLite store is provided,
preserving backward compatibility for tests and CLI usage.
"""

from datetime import datetime
from typing import Optional

from src.models.job import Job, JobStatus
from src.storage.signatures import compute_input_signature
from src.storage.sqlite_store import SQLiteStore


class JobService:
    """Manages job creation, lookup, and lifecycle transitions.

    When constructed with a SQLiteStore, all state is persisted.
    When constructed without one (store=None), falls back to
    in-memory dict storage for backward compatibility.
    """

    def __init__(self, store: Optional[SQLiteStore] = None) -> None:
        self._store = store
        # In-memory fallback (used when store is None)
        self._jobs: dict[str, Job] = {}

    @property
    def persistent(self) -> bool:
        """Whether this service is backed by persistent storage."""
        return self._store is not None

    def create_job(
        self,
        url: str,
        language: Optional[str] = None,
        skip_correction: bool = False,
        custom_terms: Optional[list[str]] = None,
        speaker_attribution: bool = False,
    ) -> Job:
        """Create a new transcription job."""
        job_id = f"job_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        job = Job(
            job_id=job_id,
            url=url,
            language=language,
            skip_correction=skip_correction,
            custom_terms=custom_terms,
            speaker_attribution=speaker_attribution,
            message="任務已建立，等待處理...",
        )

        if self._store:
            signature = compute_input_signature(
                url, language, skip_correction, custom_terms,
                speaker_attribution=speaker_attribution,
            )
            job._input_signature = signature  # noqa: SLF001
            self._store.insert_job(job)
            self._store.set_input_signature(job_id, signature)
        else:
            self._jobs[job_id] = job

        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Look up a job by ID. Returns None if not found."""
        if self._store:
            return self._store.get_job(job_id)
        return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: JobStatus,
        progress: int,
        message: str = "",
    ) -> None:
        """Update a job's lifecycle state."""
        if self._store:
            self._store.update_job_status(job_id, status, progress, message)
        else:
            job = self._jobs.get(job_id)
            if job:
                job.update(status, progress, message)

    def complete_job(self, job_id: str) -> None:
        """Mark a job as completed."""
        if self._store:
            self._store.complete_job(job_id, datetime.now().isoformat())
        else:
            job = self._jobs.get(job_id)
            if job:
                job.complete()

    def fail_job(self, job_id: str, error: str) -> None:
        """Mark a job as failed."""
        if self._store:
            self._store.fail_job(job_id, error)
        else:
            job = self._jobs.get(job_id)
            if job:
                job.fail(error)

    # ── Result persistence ────────────────────────────────────

    def store_result(self, job_id: str, result: dict) -> None:
        """Persist a job's result artifacts (no-op without store)."""
        if self._store:
            self._store.insert_result(job_id, result)

    def get_result(self, job_id: str) -> Optional[dict]:
        """Retrieve a persisted result (returns None without store)."""
        if self._store:
            return self._store.get_result(job_id)
        return None

    def store_merge_fields(self, job_id: str, merge_data: dict) -> None:
        """Persist merge-specific fields on an existing result (no-op without store)."""
        if self._store:
            self._store.update_result_merge_fields(job_id, merge_data)

    # ── Reuse lookup ──────────────────────────────────────────

    def find_reusable_job(
        self,
        url: str,
        language: Optional[str] = None,
        skip_correction: bool = False,
        custom_terms: Optional[list[str]] = None,
        speaker_attribution: bool = False,
    ) -> Optional[Job]:
        """Find a completed job with matching inputs for reuse.

        Returns the most recent matching completed job, or None.
        Reuse is not yet wired into the transcription flow —
        this provides the foundation for exact-input reuse.
        """
        if not self._store:
            return None
        signature = compute_input_signature(
            url, language, skip_correction, custom_terms,
            speaker_attribution=speaker_attribution,
        )
        return self._store.find_completed_by_signature(signature)
