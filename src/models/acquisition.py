"""Acquisition mode, failure classification, and attempt models.

Unit H1: shared vocabulary for YouTube acquisition robustness.
Later units (H2 fallback routing, H3 alternate-host execution) build on
these enums and classifiers without changing existing pipeline code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Acquisition mode – how yt-dlp is configured for a given attempt
# ---------------------------------------------------------------------------

class AcquisitionMode(str, Enum):
    """Describes the yt-dlp configuration strategy used for an attempt."""
    UNAUTHENTICATED = "unauthenticated"   # best-effort, no cookies
    COOKIE_FILE = "cookie_file"           # Netscape cookie file
    COOKIE_BROWSER = "cookie_browser"     # cookies extracted from browser
    OAUTH = "oauth"                       # future: OAuth token flow


# ---------------------------------------------------------------------------
# Failure classification
# ---------------------------------------------------------------------------

class FailureCategory(str, Enum):
    """Coarse failure bucket — drives fallback routing decisions."""
    AUTH_REQUIRED = "auth_required"       # sign-in / bot gate
    GEO_BLOCKED = "geo_blocked"          # region restriction
    UNAVAILABLE = "unavailable"          # deleted / private / copyright
    RATE_LIMITED = "rate_limited"         # HTTP 429 or throttle signals
    TRANSIENT = "transient"              # network timeout, 5xx, reload
    FORMAT_ERROR = "format_error"        # no suitable format / codec issue
    UNKNOWN = "unknown"                  # anything we can't classify


@dataclass(frozen=True)
class FailurePattern:
    """A regex pattern mapped to a failure category."""
    pattern: re.Pattern[str]
    category: FailureCategory


# Order matters: first match wins. More specific patterns come first.
_FAILURE_PATTERNS: list[FailurePattern] = [
    # --- auth / bot gate ---
    FailurePattern(re.compile(r"sign\s*in\s+to\s+confirm", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"please\s+sign\s+in", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"login\s+required", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"confirm\s+your\s+age", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"age[- ]?restrict", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"captcha", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"consent", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"bot", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"cookies", re.I), FailureCategory.AUTH_REQUIRED),
    FailurePattern(re.compile(r"use.*--cookies", re.I), FailureCategory.AUTH_REQUIRED),

    # --- transient / reload ---
    FailurePattern(re.compile(r"page\s+needs\s+to\s+be\s+reloaded", re.I), FailureCategory.TRANSIENT),
    FailurePattern(re.compile(r"connection\s+reset", re.I), FailureCategory.TRANSIENT),
    FailurePattern(re.compile(r"timed?\s*out", re.I), FailureCategory.TRANSIENT),
    FailurePattern(re.compile(r"HTTP\s+Error\s+5\d\d", re.I), FailureCategory.TRANSIENT),
    FailurePattern(re.compile(r"server\s+error", re.I), FailureCategory.TRANSIENT),
    FailurePattern(re.compile(r"incomplete\s+read", re.I), FailureCategory.TRANSIENT),

    # --- rate limited ---
    FailurePattern(re.compile(r"HTTP\s+Error\s+429", re.I), FailureCategory.RATE_LIMITED),
    FailurePattern(re.compile(r"too\s+many\s+requests", re.I), FailureCategory.RATE_LIMITED),
    FailurePattern(re.compile(r"rate[- ]?limit", re.I), FailureCategory.RATE_LIMITED),

    # --- geo block ---
    FailurePattern(re.compile(r"not\s+available\s+in\s+your\s+country", re.I), FailureCategory.GEO_BLOCKED),
    FailurePattern(re.compile(r"geo[- ]?restrict", re.I), FailureCategory.GEO_BLOCKED),
    FailurePattern(re.compile(r"blocked\s+in\s+your", re.I), FailureCategory.GEO_BLOCKED),

    # --- unavailable (deleted / private / copyright) ---
    FailurePattern(re.compile(r"video\s+(is\s+)?(unavailable|not\s+available)", re.I), FailureCategory.UNAVAILABLE),
    FailurePattern(re.compile(r"(has\s+been|was)\s+removed", re.I), FailureCategory.UNAVAILABLE),
    FailurePattern(re.compile(r"private\s+video", re.I), FailureCategory.UNAVAILABLE),
    FailurePattern(re.compile(r"copyright", re.I), FailureCategory.UNAVAILABLE),
    FailurePattern(re.compile(r"terminated", re.I), FailureCategory.UNAVAILABLE),
    FailurePattern(re.compile(r"HTTP\s+Error\s+404", re.I), FailureCategory.UNAVAILABLE),

    # --- format issues ---
    FailurePattern(re.compile(r"format\s+not\s+available", re.I), FailureCategory.FORMAT_ERROR),
    FailurePattern(re.compile(r"no\s+suitable\s+format", re.I), FailureCategory.FORMAT_ERROR),
    FailurePattern(re.compile(r"requested\s+format\s+not\s+available", re.I), FailureCategory.FORMAT_ERROR),
]


def classify_failure(error_msg: str) -> FailureCategory:
    """Classify a yt-dlp error message into a FailureCategory.

    Returns FailureCategory.UNKNOWN if no pattern matches.
    First matching pattern wins (most-specific patterns listed first).
    """
    for fp in _FAILURE_PATTERNS:
        if fp.pattern.search(error_msg):
            return fp.category
    return FailureCategory.UNKNOWN


def is_retryable(category: FailureCategory) -> bool:
    """Whether a failure category is worth retrying (possibly with escalation).

    AUTH_REQUIRED → retryable with mode escalation (add cookies).
    TRANSIENT     → retryable with same mode (network flake).
    RATE_LIMITED  → retryable after backoff.
    Others        → not retryable.
    """
    return category in {
        FailureCategory.AUTH_REQUIRED,
        FailureCategory.TRANSIENT,
        FailureCategory.RATE_LIMITED,
    }


# ---------------------------------------------------------------------------
# Acquisition attempt – single try record
# ---------------------------------------------------------------------------

@dataclass
class AcquisitionAttempt:
    """Record of a single acquisition attempt for audit/fallback decisions."""
    mode: AcquisitionMode
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: Optional[str] = None
    success: bool = False
    error_message: Optional[str] = None
    failure_category: Optional[FailureCategory] = None

    def record_success(self) -> None:
        self.finished_at = datetime.now().isoformat()
        self.success = True

    def record_failure(self, error_msg: str) -> None:
        self.finished_at = datetime.now().isoformat()
        self.success = False
        self.error_message = error_msg
        self.failure_category = classify_failure(error_msg)


# ---------------------------------------------------------------------------
# Fallback decision hint (foundation for H2)
# ---------------------------------------------------------------------------

class FallbackAction(str, Enum):
    """What the orchestrator should do after a failed attempt.

    H2 will implement the routing logic; H1 just defines the vocabulary.
    """
    RETRY_SAME_MODE = "retry_same_mode"       # transient – try again
    ESCALATE_AUTH = "escalate_auth"            # add cookies / upgrade mode
    ABORT = "abort"                            # non-retryable failure
    WAIT_AND_RETRY = "wait_and_retry"          # rate-limited – back off


def suggest_fallback(category: FailureCategory, auth_configured: bool) -> FallbackAction:
    """Suggest a fallback action based on failure category and current auth state.

    This is a pure-function hint for H2's routing logic.
    """
    if category == FailureCategory.AUTH_REQUIRED:
        if auth_configured:
            # Auth was already tried and still failed
            return FallbackAction.ABORT
        return FallbackAction.ESCALATE_AUTH

    if category == FailureCategory.TRANSIENT:
        return FallbackAction.RETRY_SAME_MODE

    if category == FailureCategory.RATE_LIMITED:
        return FallbackAction.WAIT_AND_RETRY

    # GEO_BLOCKED, UNAVAILABLE, FORMAT_ERROR, UNKNOWN → abort
    return FallbackAction.ABORT
