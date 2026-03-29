"""Fallback decision policy — maps acquisition diagnostics to next actions.

Unit H3: centralises the routing logic that decides what to try after
this-host acquisition fails.  The policy inspects an AcquisitionResult
(from H2) and produces a FallbackDecision with an explicit action,
operator-visible reason, and enough metadata for H4/H5 to act on.

Design principles:
  1. Improve this-host path first (retry / escalate auth).
  2. When this host cannot proceed, surface ``MANUAL_FALLBACK`` with a clear reason
     (no remote full-pipeline delegation).
  3. Decisions are semi-automatic: every decision carries a human-readable
     reason so operators can audit the routing logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.models.acquisition import (
    AcquisitionMode,
    FailureCategory,
    FallbackAction,
)
from src.services.acquisition_service import AcquisitionResult, auth_configured


# ---------------------------------------------------------------------------
# Decision vocabulary
# ---------------------------------------------------------------------------

class FallbackRoute(str, Enum):
    """Where to direct the next acquisition attempt."""
    RETRY_THIS_HOST = "retry_this_host"
    ESCALATE_AUTH_THIS_HOST = "escalate_auth_this_host"
    WAIT_RETRY_THIS_HOST = "wait_retry_this_host"
    MANUAL_FALLBACK = "manual_fallback"
    ABORT = "abort"


@dataclass(frozen=True)
class FallbackDecision:
    """Operator-visible decision object produced by the policy layer.

    Attributes:
        route: The recommended next action.
        reason: Human-readable explanation of *why* this route was chosen.
        failure_category: The classified failure that triggered the decision.
        retry_mode: If route involves a this-host retry, which mode to use.
        wait_seconds: Suggested backoff if route is WAIT_RETRY_THIS_HOST.
        exhausted_modes: Modes already attempted on this host.
    """
    route: FallbackRoute
    reason: str
    failure_category: Optional[FailureCategory] = None
    retry_mode: Optional[AcquisitionMode] = None
    wait_seconds: int = 0
    exhausted_modes: tuple[AcquisitionMode, ...] = ()


# ---------------------------------------------------------------------------
# Policy implementation
# ---------------------------------------------------------------------------

_DEFAULT_RATE_LIMIT_WAIT = 30  # seconds


def decide(result: AcquisitionResult) -> FallbackDecision:
    """Evaluate an AcquisitionResult and return a FallbackDecision.

    This is the single entry point for the H3 policy layer.  It inspects
    the full attempt history (not just the last failure) to make a
    well-informed routing decision.
    """
    if result.success:
        return FallbackDecision(
            route=FallbackRoute.ABORT,
            reason="Acquisition succeeded — no fallback needed.",
        )

    if not result.attempts:
        return FallbackDecision(
            route=FallbackRoute.RETRY_THIS_HOST,
            reason="No attempts recorded — retry on this host.",
            retry_mode=AcquisitionMode.UNAUTHENTICATED,
        )

    exhausted = tuple(a.mode for a in result.attempts)
    category = result.last_failure_category

    if category is None:
        return FallbackDecision(
            route=FallbackRoute.ABORT,
            reason="Failure could not be classified — aborting.",
            exhausted_modes=exhausted,
        )

    return _route_by_category(category, exhausted)


def _route_by_category(
    category: FailureCategory,
    exhausted: tuple[AcquisitionMode, ...],
) -> FallbackDecision:
    """Core routing table: failure category × host state → decision."""

    has_auth = auth_configured()
    tried_auth = any(
        m in {AcquisitionMode.COOKIE_FILE, AcquisitionMode.COOKIE_BROWSER, AcquisitionMode.OAUTH}
        for m in exhausted
    )

    # --- AUTH_REQUIRED ---
    if category == FailureCategory.AUTH_REQUIRED:
        if has_auth and not tried_auth:
            return FallbackDecision(
                route=FallbackRoute.ESCALATE_AUTH_THIS_HOST,
                reason="Auth required and credentials available but not yet tried — escalating on this host.",
                failure_category=category,
                retry_mode=_pick_auth_mode(),
                exhausted_modes=exhausted,
            )
        if has_auth and tried_auth:
            return FallbackDecision(
                route=FallbackRoute.MANUAL_FALLBACK,
                reason="Auth required and credentials were tried but failed — try another network, refresh cookies, or another machine.",
                failure_category=category,
                exhausted_modes=exhausted,
            )
        return FallbackDecision(
            route=FallbackRoute.MANUAL_FALLBACK,
            reason="Auth required but no YouTube cookies configured on this host — set YT_DLP_COOKIES_FILE or YT_DLP_COOKIES_FROM_BROWSER, or run on another host.",
            failure_category=category,
            exhausted_modes=exhausted,
        )

    # --- TRANSIENT ---
    if category == FailureCategory.TRANSIENT:
        # Transient failures are worth one more local retry, then delegate
        if len(exhausted) < 3:
            last_mode = exhausted[-1] if exhausted else AcquisitionMode.UNAUTHENTICATED
            return FallbackDecision(
                route=FallbackRoute.RETRY_THIS_HOST,
                reason=f"Transient failure (attempt {len(exhausted)}) — retrying on this host.",
                failure_category=category,
                retry_mode=last_mode,
                exhausted_modes=exhausted,
            )
        return FallbackDecision(
            route=FallbackRoute.MANUAL_FALLBACK,
            reason="Transient failure persisted after multiple attempts — retry later or retry from another network/host.",
            failure_category=category,
            exhausted_modes=exhausted,
        )

    # --- RATE_LIMITED ---
    if category == FailureCategory.RATE_LIMITED:
        if len(exhausted) < 2:
            return FallbackDecision(
                route=FallbackRoute.WAIT_RETRY_THIS_HOST,
                reason="Rate-limited — backing off before retrying on this host.",
                failure_category=category,
                retry_mode=exhausted[-1] if exhausted else AcquisitionMode.UNAUTHENTICATED,
                wait_seconds=_DEFAULT_RATE_LIMIT_WAIT,
                exhausted_modes=exhausted,
            )
        return FallbackDecision(
            route=FallbackRoute.MANUAL_FALLBACK,
            reason="Rate-limited repeatedly — wait and retry, or use another IP/host.",
            failure_category=category,
            exhausted_modes=exhausted,
        )

    # --- GEO_BLOCKED ---
    if category == FailureCategory.GEO_BLOCKED:
        return FallbackDecision(
            route=FallbackRoute.MANUAL_FALLBACK,
            reason="Geo-blocked on this host — try a VPN/region that can access the video, or another machine.",
            failure_category=category,
            exhausted_modes=exhausted,
        )

    # --- UNAVAILABLE ---
    if category == FailureCategory.UNAVAILABLE:
        return FallbackDecision(
            route=FallbackRoute.ABORT,
            reason="Video is unavailable (deleted/private/copyright) — no fallback will help.",
            failure_category=category,
            exhausted_modes=exhausted,
        )

    # --- FORMAT_ERROR ---
    if category == FailureCategory.FORMAT_ERROR:
        return FallbackDecision(
            route=FallbackRoute.MANUAL_FALLBACK,
            reason="Format not available — operator may need to adjust format/quality settings.",
            failure_category=category,
            exhausted_modes=exhausted,
        )

    # --- UNKNOWN ---
    return FallbackDecision(
        route=FallbackRoute.MANUAL_FALLBACK,
        reason="Unclassified failure — operator review recommended.",
        failure_category=category,
        exhausted_modes=exhausted,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pick_auth_mode() -> AcquisitionMode:
    """Return the best auth mode available on this host."""
    import os
    if os.environ.get("YT_DLP_COOKIES_FILE"):
        return AcquisitionMode.COOKIE_FILE
    if os.environ.get("YT_DLP_COOKIES_FROM_BROWSER"):
        return AcquisitionMode.COOKIE_BROWSER
    return AcquisitionMode.UNAUTHENTICATED
