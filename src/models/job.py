"""Canonical job model for transcription lifecycle."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class JobStatus(str, Enum):
    """Job lifecycle states."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    CORRECTING = "correcting"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    """Represents a transcription job with lifecycle state.

    This is the canonical job model used by both CLI and API.
    Currently backed by in-memory storage; designed for future
    SQLite persistence (Unit 2).
    """
    job_id: str
    url: str
    status: JobStatus = JobStatus.PENDING
    progress: int = 0  # 0-100
    message: str = ""
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    # Input parameters (used for future reuse/signature matching)
    language: Optional[str] = None
    skip_correction: bool = False
    custom_terms: Optional[list[str]] = None
    speaker_attribution: bool = False
    speaker_strategy: Optional[str] = None

    def update(self, status: JobStatus, progress: int, message: str = "") -> None:
        """Update job state."""
        self.status = status
        self.progress = progress
        self.message = message

    def complete(self) -> None:
        """Mark job as completed."""
        self.status = JobStatus.COMPLETED
        self.progress = 100
        self.message = "處理完成"
        self.completed_at = datetime.now().isoformat()

    def fail(self, error: str) -> None:
        """Mark job as failed."""
        self.status = JobStatus.FAILED
        self.message = f"錯誤: {error}"
        self.error = error
