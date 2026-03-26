"""HTTP backup-service delegation contract models.

Unit H7a: defines the request/response contract for delegating a full
transcription job to a backup service on the same internal network.

Unlike H4 (alternate-host acquisition), this is *service-level* delegation:
the backup service runs the complete pipeline (acquisition → transcription
→ correction) and returns the final result.

Design principles:
  1. The request carries everything the backup service needs to run the
     full pipeline — URL, language, correction preferences, and context
     about why delegation happened.
  2. The response wraps the final transcript result plus delegation
     metadata so the caller can relay it transparently.
  3. Models are frozen dataclasses with to_dict/from_dict for JSON
     serialisation, following the same pattern as H4.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from src.models.acquisition import FailureCategory


# ---------------------------------------------------------------------------
# Delegation status
# ---------------------------------------------------------------------------

class DelegationStatus(str, Enum):
    """Outcome of a delegated transcription job."""
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"  # backup refused (overloaded, auth invalid, etc.)


# ---------------------------------------------------------------------------
# Request contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DelegationRequest:
    """What the primary service sends to the backup service.

    Attributes:
        url: YouTube URL to transcribe.
        language: Whisper language hint (None = auto-detect).
        skip_correction: Whether to skip GPT text correction.
        custom_terms: Domain terms to preserve during correction.
        originator: Identifier for the calling host (audit trail).
        delegation_reason: Why the primary service is delegating.
        acquisition_failure_context: Optional summary of local failures.
        job_id: Caller-generated correlation ID (optional).
    """
    url: str
    language: Optional[str] = None
    skip_correction: bool = False
    custom_terms: tuple[str, ...] = ()
    originator: str = ""
    delegation_reason: str = ""
    acquisition_failure_context: Optional[str] = None
    job_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "language": self.language,
            "skip_correction": self.skip_correction,
            "custom_terms": list(self.custom_terms),
            "originator": self.originator,
            "delegation_reason": self.delegation_reason,
            "acquisition_failure_context": self.acquisition_failure_context,
            "job_id": self.job_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> DelegationRequest:
        return cls(
            url=data["url"],
            language=data.get("language"),
            skip_correction=data.get("skip_correction", False),
            custom_terms=tuple(data.get("custom_terms", ())),
            originator=data.get("originator", ""),
            delegation_reason=data.get("delegation_reason", ""),
            acquisition_failure_context=data.get("acquisition_failure_context"),
            job_id=data.get("job_id"),
        )

    @classmethod
    def from_json(cls, raw: str) -> DelegationRequest:
        return cls.from_dict(json.loads(raw))


# ---------------------------------------------------------------------------
# Result payload (nested in response)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DelegationResult:
    """Transcript result returned by the backup service on success.

    Mirrors the fields the primary service would produce locally so the
    caller can relay the result transparently.
    """
    video_id: str = ""
    title: str = ""
    channel: str = ""
    duration: int = 0
    original_text: str = ""
    corrected_text: str = ""
    language: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> DelegationResult:
        return cls(
            video_id=data.get("video_id", ""),
            title=data.get("title", ""),
            channel=data.get("channel", ""),
            duration=data.get("duration", 0),
            original_text=data.get("original_text", ""),
            corrected_text=data.get("corrected_text", ""),
            language=data.get("language", ""),
        )


# ---------------------------------------------------------------------------
# Response contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DelegationResponse:
    """What the backup service returns after processing a delegation request.

    Attributes:
        status: Overall outcome.
        delegated: Always True (confirms this was a delegated job).
        remote_host: Identifier for the backup host that processed the job.
        result: Transcript result on success, None on failure.
        error_message: Human-readable error on failure.
        failure_category: Classified failure category (if applicable).
        acquisition_diagnostics: Optional diagnostic summary from the
            backup host's acquisition phase.
    """
    status: DelegationStatus
    delegated: bool = True
    remote_host: str = ""
    result: Optional[DelegationResult] = None
    error_message: Optional[str] = None
    failure_category: Optional[FailureCategory] = None
    acquisition_diagnostics: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == DelegationStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "delegated": self.delegated,
            "remote_host": self.remote_host,
            "result": self.result.to_dict() if self.result else None,
            "error_message": self.error_message,
            "failure_category": (
                self.failure_category.value if self.failure_category else None
            ),
            "acquisition_diagnostics": self.acquisition_diagnostics,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> DelegationResponse:
        status = DelegationStatus(data["status"])

        result = data.get("result")
        if result is not None:
            result = DelegationResult.from_dict(result)

        cat = data.get("failure_category")
        if cat is not None:
            cat = FailureCategory(cat)

        return cls(
            status=status,
            delegated=data.get("delegated", True),
            remote_host=data.get("remote_host", ""),
            result=result,
            error_message=data.get("error_message"),
            failure_category=cat,
            acquisition_diagnostics=data.get("acquisition_diagnostics"),
        )

    @classmethod
    def from_json(cls, raw: str) -> DelegationResponse:
        return cls.from_dict(json.loads(raw))
