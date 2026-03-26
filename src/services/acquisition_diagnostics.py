"""Operator-facing diagnostics formatters for acquisition outcomes.

Unit H6: provides human-readable and serialisable summaries so operators
and future sessions can quickly understand what happened during acquisition
and what to do next.
"""

from __future__ import annotations

from typing import Optional

from src.models.acquisition import FailureCategory
from src.services.acquisition_service import AcquisitionResult
from src.services.fallback_policy import FallbackDecision, FallbackRoute


# ---------------------------------------------------------------------------
# Operator guidance per failure category
# ---------------------------------------------------------------------------

_OPERATOR_GUIDANCE: dict[FailureCategory, str] = {
    FailureCategory.AUTH_REQUIRED: (
        "Configure YT_DLP_COOKIES_FILE or YT_DLP_COOKIES_FROM_BROWSER, "
        "or delegate to an alternate host with valid credentials."
    ),
    FailureCategory.GEO_BLOCKED: (
        "This video is region-restricted. Acquire from a host in an allowed region."
    ),
    FailureCategory.UNAVAILABLE: (
        "The video is deleted, private, or copyright-struck. Verify the URL is correct; "
        "no retry will help."
    ),
    FailureCategory.RATE_LIMITED: (
        "Reduce request frequency or wait before retrying. "
        "If persistent, rotate IP or delegate to alternate host."
    ),
    FailureCategory.TRANSIENT: (
        "Usually self-resolving. Check network connectivity if failures persist."
    ),
    FailureCategory.FORMAT_ERROR: (
        "Try different format or quality settings. Some videos lack certain codecs."
    ),
    FailureCategory.UNKNOWN: (
        "Review the raw error message. A new classification pattern may be needed "
        "in src/models/acquisition.py."
    ),
}

_ROUTE_LABELS: dict[FallbackRoute, str] = {
    FallbackRoute.RETRY_THIS_HOST: "Retry on this host (same mode)",
    FallbackRoute.ESCALATE_AUTH_THIS_HOST: "Retry on this host with auth credentials",
    FallbackRoute.WAIT_RETRY_THIS_HOST: "Wait then retry on this host",
    FallbackRoute.DELEGATE_ALTERNATE_HOST: "Delegate to alternate acquisition host",
    FallbackRoute.MANUAL_FALLBACK: "Manual operator intervention required",
    FallbackRoute.ABORT: "No further action — acquisition cannot proceed",
}


# ---------------------------------------------------------------------------
# Serialisable diagnostics dict
# ---------------------------------------------------------------------------

def build_diagnostics_dict(
    result: AcquisitionResult,
    decision: Optional[FallbackDecision] = None,
) -> dict:
    """Build a JSON-serialisable diagnostics dict for logging or API responses.

    Combines the acquisition attempt history with the fallback decision and
    operator guidance into a single flat structure.
    """
    base = result.diagnostics()

    category = result.last_failure_category
    guidance = _OPERATOR_GUIDANCE.get(category, "") if category else ""

    base["failure_category"] = category.value if category else None
    base["operator_guidance"] = guidance

    if decision:
        base["fallback"] = {
            "route": decision.route.value,
            "label": _ROUTE_LABELS.get(decision.route, decision.route.value),
            "reason": decision.reason,
            "wait_seconds": decision.wait_seconds,
            "exhausted_modes": [m.value for m in decision.exhausted_modes],
        }
    else:
        base["fallback"] = None

    return base


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def format_operator_summary(
    result: AcquisitionResult,
    decision: Optional[FallbackDecision] = None,
) -> str:
    """Format a concise, human-readable summary for operator/log output.

    Example output::

        Acquisition: FAILED (2 attempts)
          1. unauthenticated  FAIL  auth_required  "Sign in to confirm..."
          2. cookie_file      FAIL  auth_required  "Sign in to confirm..."
        Failure: auth_required
        Decision: delegate_alternate_host
          Reason: Auth required, credentials tried but failed.
        Guidance: Configure YT_DLP_COOKIES_FILE or ...
    """
    lines: list[str] = []

    # Header
    status = "OK" if result.success else "FAILED"
    lines.append(f"Acquisition: {status} ({result.strategy_count} attempt(s))")

    # Attempt details
    for i, attempt in enumerate(result.attempts, 1):
        outcome = "OK" if attempt.success else "FAIL"
        cat = attempt.failure_category.value if attempt.failure_category else "-"
        err = _truncate(attempt.error_message, 60) if attempt.error_message else ""
        err_part = f'  "{err}"' if err else ""
        lines.append(f"  {i}. {attempt.mode.value:<18} {outcome:<4}  {cat}{err_part}")

    # Failure category
    category = result.last_failure_category
    if category:
        lines.append(f"Failure: {category.value}")

    # Decision
    if decision:
        label = _ROUTE_LABELS.get(decision.route, decision.route.value)
        lines.append(f"Decision: {decision.route.value}")
        lines.append(f"  {label}")
        lines.append(f"  Reason: {decision.reason}")
        if decision.wait_seconds:
            lines.append(f"  Wait: {decision.wait_seconds}s before retry")

    # Guidance
    if category:
        guidance = _OPERATOR_GUIDANCE.get(category, "")
        if guidance:
            lines.append(f"Guidance: {guidance}")

    return "\n".join(lines)


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."
