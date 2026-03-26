"""Alternate-host acquisition request/response contract.

Unit H4: defines the URL-based handoff contract for delegating YouTube
acquisition to an alternate always-on host.  This module is a *contract
boundary* — it specifies what data crosses the wire, not how the wire
works.  A future transport layer (HTTP client, message queue, etc.) will
consume these models to perform the actual remote call.

Design principles:
  1. The request carries only the YouTube URL and acquisition preferences —
     no transcript-pipeline details leak across the boundary.
  2. The response mirrors the shape of a local AcquisitionResult so the
     orchestrator can treat local and remote outcomes uniformly.
  3. Models are frozen dataclasses that serialise to/from plain dicts
     (JSON-ready) without external dependencies.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

from src.models.acquisition import (
    AcquisitionMode,
    FailureCategory,
)


# ---------------------------------------------------------------------------
# Request contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AlternateHostRequest:
    """What this host sends to the alternate acquisition host.

    Attributes:
        url: The YouTube URL to acquire.
        preferred_mode: Hint for how the remote host should attempt extraction.
            None means "use your default strategy order".
        format: Desired audio format (e.g. "mp3", "m4a").
        quality: Desired audio quality in kbps (e.g. "64", "128").
        download: Whether the remote host should download media or just
            extract metadata.
        originator: Identifier for the requesting host (for audit trails).
        failure_context: Optional summary of why this host couldn't acquire
            locally — helps the remote host pick a better strategy.
    """
    url: str
    preferred_mode: Optional[AcquisitionMode] = None
    format: str = "mp3"
    quality: str = "64"
    download: bool = True
    originator: str = ""
    failure_context: Optional[FailureContext] = None

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        d = asdict(self)
        if d["preferred_mode"] is not None:
            d["preferred_mode"] = d["preferred_mode"]
        if d["failure_context"] is not None:
            d["failure_context"] = self.failure_context.to_dict()
        return d

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> AlternateHostRequest:
        """Deserialise from a plain dict."""
        mode = data.get("preferred_mode")
        if mode is not None:
            mode = AcquisitionMode(mode)

        fc = data.get("failure_context")
        if fc is not None:
            fc = FailureContext.from_dict(fc)

        return cls(
            url=data["url"],
            preferred_mode=mode,
            format=data.get("format", "mp3"),
            quality=data.get("quality", "64"),
            download=data.get("download", True),
            originator=data.get("originator", ""),
            failure_context=fc,
        )

    @classmethod
    def from_json(cls, raw: str) -> AlternateHostRequest:
        """Deserialise from a JSON string."""
        return cls.from_dict(json.loads(raw))


@dataclass(frozen=True)
class FailureContext:
    """Summary of why the originating host failed — forwarded to the remote.

    This is *not* the full AcquisitionResult; it's a trimmed-down digest
    so the remote host can make an informed strategy choice without
    receiving the full attempt log.
    """
    last_category: Optional[FailureCategory] = None
    exhausted_modes: tuple[AcquisitionMode, ...] = ()
    attempt_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "last_category": self.last_category.value if self.last_category else None,
            "exhausted_modes": [m.value for m in self.exhausted_modes],
            "attempt_count": self.attempt_count,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FailureContext:
        cat = data.get("last_category")
        if cat is not None:
            cat = FailureCategory(cat)
        modes = tuple(AcquisitionMode(m) for m in data.get("exhausted_modes", []))
        return cls(
            last_category=cat,
            exhausted_modes=modes,
            attempt_count=data.get("attempt_count", 0),
            reason=data.get("reason", ""),
        )


# ---------------------------------------------------------------------------
# Response contract
# ---------------------------------------------------------------------------

class RemoteAcquisitionStatus(str, Enum):
    """Outcome status from the remote host."""
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"  # remote host refused the request (e.g. overloaded)


@dataclass(frozen=True)
class RemoteVideoInfo:
    """Minimal video metadata returned by the remote host.

    Mirrors the shape of the local VideoInfo but only includes fields
    needed for the transcript pipeline to continue.
    """
    video_id: str = ""
    title: str = ""
    duration: int = 0
    channel: str = ""
    audio_url: Optional[str] = None  # URL where the downloaded audio can be fetched

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RemoteVideoInfo:
        return cls(
            video_id=data.get("video_id", ""),
            title=data.get("title", ""),
            duration=data.get("duration", 0),
            channel=data.get("channel", ""),
            audio_url=data.get("audio_url"),
        )


@dataclass(frozen=True)
class AlternateHostResponse:
    """What the alternate host sends back after processing a request.

    Attributes:
        status: Overall outcome.
        video_info: Metadata on success, None on failure.
        error_message: Human-readable error on failure.
        failure_category: Classified failure (if the remote host classifies).
        remote_host: Identifier for which host processed the request.
    """
    status: RemoteAcquisitionStatus
    video_info: Optional[RemoteVideoInfo] = None
    error_message: Optional[str] = None
    failure_category: Optional[FailureCategory] = None
    remote_host: str = ""

    @property
    def success(self) -> bool:
        return self.status == RemoteAcquisitionStatus.SUCCESS

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "video_info": self.video_info.to_dict() if self.video_info else None,
            "error_message": self.error_message,
            "failure_category": (
                self.failure_category.value if self.failure_category else None
            ),
            "remote_host": self.remote_host,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> AlternateHostResponse:
        status = RemoteAcquisitionStatus(data["status"])

        vi = data.get("video_info")
        if vi is not None:
            vi = RemoteVideoInfo.from_dict(vi)

        cat = data.get("failure_category")
        if cat is not None:
            cat = FailureCategory(cat)

        return cls(
            status=status,
            video_info=vi,
            error_message=data.get("error_message"),
            failure_category=cat,
            remote_host=data.get("remote_host", ""),
        )

    @classmethod
    def from_json(cls, raw: str) -> AlternateHostResponse:
        return cls.from_dict(json.loads(raw))


# ---------------------------------------------------------------------------
# Factory helpers — bridge from H3 decision to H4 request
# ---------------------------------------------------------------------------

def build_request_from_decision(
    url: str,
    *,
    failure_category: Optional[FailureCategory] = None,
    exhausted_modes: tuple[AcquisitionMode, ...] = (),
    attempt_count: int = 0,
    reason: str = "",
    originator: str = "",
    format: str = "mp3",
    quality: str = "64",
    download: bool = True,
) -> AlternateHostRequest:
    """Construct an AlternateHostRequest from H3 FallbackDecision fields.

    This is the recommended way to create a request when the fallback
    policy has decided to delegate to an alternate host.
    """
    ctx = FailureContext(
        last_category=failure_category,
        exhausted_modes=exhausted_modes,
        attempt_count=attempt_count,
        reason=reason,
    ) if (failure_category or exhausted_modes or reason) else None

    return AlternateHostRequest(
        url=url,
        format=format,
        quality=quality,
        download=download,
        originator=originator,
        failure_context=ctx,
    )
