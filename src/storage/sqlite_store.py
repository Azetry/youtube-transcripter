"""SQLite-backed store for job and result persistence.

Provides CRUD operations for jobs and their results, backed by
the schema defined in schema.py. Thread-safe via SQLite's WAL mode
and check_same_thread=False.
"""

import json
import sqlite3
import threading
from typing import Optional

from src.models.job import Job, JobStatus


class SQLiteStore:
    """Persistent store for transcription jobs and results."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.Lock()

    # ── Job CRUD ──────────────────────────────────────────────

    def insert_job(self, job: Job) -> None:
        """Insert a new job row."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO jobs
                   (job_id, url, status, progress, message, error,
                    created_at, completed_at,
                    language, skip_correction, custom_terms, input_signature)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job.job_id,
                    job.url,
                    job.status.value,
                    job.progress,
                    job.message,
                    job.error,
                    job.created_at,
                    job.completed_at,
                    job.language,
                    int(job.skip_correction),
                    json.dumps(job.custom_terms) if job.custom_terms else None,
                    getattr(job, "_input_signature", None),
                ),
            )
            self._conn.commit()

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID. Returns None if not found."""
        cur = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: int,
        message: str = "",
    ) -> None:
        """Update a job's lifecycle state."""
        with self._lock:
            self._conn.execute(
                """UPDATE jobs
                   SET status = ?, progress = ?, message = ?
                   WHERE job_id = ?""",
                (status.value, progress, message, job_id),
            )
            self._conn.commit()

    def complete_job(self, job_id: str, completed_at: str) -> None:
        """Mark a job as completed."""
        with self._lock:
            self._conn.execute(
                """UPDATE jobs
                   SET status = ?, progress = 100, message = ?, completed_at = ?
                   WHERE job_id = ?""",
                (JobStatus.COMPLETED.value, "處理完成", completed_at, job_id),
            )
            self._conn.commit()

    def fail_job(self, job_id: str, error: str) -> None:
        """Mark a job as failed with error details."""
        with self._lock:
            self._conn.execute(
                """UPDATE jobs
                   SET status = ?, message = ?, error = ?
                   WHERE job_id = ?""",
                (JobStatus.FAILED.value, f"錯誤: {error}", error, job_id),
            )
            self._conn.commit()

    # ── Result persistence ────────────────────────────────────

    def insert_result(self, job_id: str, result: dict) -> None:
        """Persist a job's result artifacts.

        Args:
            job_id: The job this result belongs to.
            result: Dict with keys matching job_results columns:
                video_id, title, channel, duration, original_text,
                corrected_text, language, similarity_ratio,
                change_count, diff_inline, processed_at.
        """
        with self._lock:
            self._conn.execute(
                """INSERT INTO job_results
                   (job_id, video_id, title, channel, duration,
                    original_text, corrected_text, language,
                    similarity_ratio, change_count, diff_inline, processed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    result["video_id"],
                    result["title"],
                    result["channel"],
                    result["duration"],
                    result["original_text"],
                    result["corrected_text"],
                    result["language"],
                    result["similarity_ratio"],
                    result["change_count"],
                    result["diff_inline"],
                    result["processed_at"],
                ),
            )
            self._conn.commit()

    def get_result(self, job_id: str) -> Optional[dict]:
        """Retrieve a job's result. Returns None if not found."""
        cur = self._conn.execute(
            "SELECT * FROM job_results WHERE job_id = ?", (job_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return dict(row)

    # ── Input signature / reuse ───────────────────────────────

    def set_input_signature(self, job_id: str, signature: str) -> None:
        """Store the input signature for a job."""
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET input_signature = ? WHERE job_id = ?",
                (signature, job_id),
            )
            self._conn.commit()

    def find_completed_by_signature(self, signature: str) -> Optional[Job]:
        """Find a completed job with matching input signature.

        Returns the most recently completed job, or None.
        """
        cur = self._conn.execute(
            """SELECT * FROM jobs
               WHERE input_signature = ? AND status = ?
               ORDER BY completed_at DESC LIMIT 1""",
            (signature, JobStatus.COMPLETED.value),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    # ── Chunk persistence ─────────────────────────────────────

    def insert_chunks(self, job_id: str, chunks: list[dict]) -> None:
        """Persist chunk metadata for a job.

        Args:
            job_id: The parent job ID.
            chunks: List of dicts with keys: chunk_index, start_time,
                    end_time, duration, audio_path (optional).
        """
        with self._lock:
            self._conn.executemany(
                """INSERT INTO job_chunks
                   (job_id, chunk_index, start_time, end_time, duration, audio_path, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'planned')""",
                [
                    (
                        job_id,
                        c["chunk_index"],
                        c["start_time"],
                        c["end_time"],
                        c["duration"],
                        c.get("audio_path"),
                    )
                    for c in chunks
                ],
            )
            self._conn.commit()

    def get_chunks(self, job_id: str) -> list[dict]:
        """Retrieve all chunks for a job, ordered by index."""
        cur = self._conn.execute(
            """SELECT * FROM job_chunks
               WHERE job_id = ?
               ORDER BY chunk_index""",
            (job_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def update_chunk_status(
        self,
        job_id: str,
        chunk_index: int,
        status: str,
        transcript_path: Optional[str] = None,
        corrected_path: Optional[str] = None,
    ) -> None:
        """Update a chunk's processing status and optional artifact paths."""
        with self._lock:
            fields = ["status = ?"]
            params: list = [status]

            if transcript_path is not None:
                fields.append("transcript_path = ?")
                params.append(transcript_path)
            if corrected_path is not None:
                fields.append("corrected_path = ?")
                params.append(corrected_path)

            params.extend([job_id, chunk_index])
            self._conn.execute(
                f"""UPDATE job_chunks
                    SET {', '.join(fields)}
                    WHERE job_id = ? AND chunk_index = ?""",
                params,
            )
            self._conn.commit()

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        """Convert a database row to a Job dataclass."""
        custom_terms = None
        if row["custom_terms"]:
            custom_terms = json.loads(row["custom_terms"])

        job = Job(
            job_id=row["job_id"],
            url=row["url"],
            status=JobStatus(row["status"]),
            progress=row["progress"],
            message=row["message"],
            error=row["error"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            language=row["language"],
            skip_correction=bool(row["skip_correction"]),
            custom_terms=custom_terms,
        )
        return job
