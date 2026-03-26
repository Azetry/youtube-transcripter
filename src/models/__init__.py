"""Canonical job and transcript models."""

from .job import Job, JobStatus
from .transcript import TranscriptArtifacts
from .acquisition import (
    AcquisitionAttempt,
    AcquisitionMode,
    FailureCategory,
    FallbackAction,
    classify_failure,
    is_retryable,
    suggest_fallback,
)

__all__ = [
    'Job',
    'JobStatus',
    'TranscriptArtifacts',
    'AcquisitionAttempt',
    'AcquisitionMode',
    'FailureCategory',
    'FallbackAction',
    'classify_failure',
    'is_retryable',
    'suggest_fallback',
]
