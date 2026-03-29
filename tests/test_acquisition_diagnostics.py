"""Tests for the operator-facing acquisition diagnostics formatter (H6)."""

import pytest

from src.models.acquisition import (
    AcquisitionAttempt,
    AcquisitionMode,
    FailureCategory,
    FallbackAction,
)
from src.services.acquisition_service import AcquisitionResult
from src.services.fallback_policy import FallbackDecision, FallbackRoute
from src.services.acquisition_diagnostics import (
    build_diagnostics_dict,
    format_operator_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_failed_result(
    modes: list[AcquisitionMode],
    error: str = "Sign in to confirm your age",
    category: FailureCategory = FailureCategory.AUTH_REQUIRED,
) -> AcquisitionResult:
    """Build an AcquisitionResult where all attempts failed."""
    result = AcquisitionResult(success=False)
    for mode in modes:
        attempt = AcquisitionAttempt(mode=mode)
        attempt.record_failure(error)
        result.attempts.append(attempt)
    result.final_action = FallbackAction.ABORT
    return result


def _make_success_result() -> AcquisitionResult:
    result = AcquisitionResult(success=True)
    attempt = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
    attempt.record_success()
    result.attempts.append(attempt)
    return result


def _make_decision(
    route: FallbackRoute = FallbackRoute.MANUAL_FALLBACK,
    reason: str = "Auth required, credentials tried but failed.",
    category: FailureCategory = FailureCategory.AUTH_REQUIRED,
    wait_seconds: int = 0,
    exhausted: tuple[AcquisitionMode, ...] = (
        AcquisitionMode.UNAUTHENTICATED,
        AcquisitionMode.COOKIE_FILE,
    ),
) -> FallbackDecision:
    return FallbackDecision(
        route=route,
        reason=reason,
        failure_category=category,
        wait_seconds=wait_seconds,
        exhausted_modes=exhausted,
    )


# ---------------------------------------------------------------------------
# build_diagnostics_dict
# ---------------------------------------------------------------------------

class TestBuildDiagnosticsDict:
    def test_success_result(self):
        result = _make_success_result()
        d = build_diagnostics_dict(result)

        assert d["success"] is True
        assert d["failure_category"] is None
        assert d["operator_guidance"] == ""
        assert d["fallback"] is None

    def test_failed_with_decision(self):
        result = _make_failed_result(
            [AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE],
        )
        decision = _make_decision()
        d = build_diagnostics_dict(result, decision)

        assert d["success"] is False
        assert d["failure_category"] == "auth_required"
        assert "YT_DLP_COOKIES_FILE" in d["operator_guidance"]
        assert d["fallback"]["route"] == "manual_fallback"
        assert d["fallback"]["reason"] == decision.reason
        assert d["fallback"]["exhausted_modes"] == ["unauthenticated", "cookie_file"]

    def test_failed_without_decision(self):
        result = _make_failed_result([AcquisitionMode.UNAUTHENTICATED])
        d = build_diagnostics_dict(result)

        assert d["success"] is False
        assert d["failure_category"] == "auth_required"
        assert d["fallback"] is None

    def test_all_categories_have_guidance(self):
        """Every FailureCategory should produce non-empty guidance."""
        for cat in FailureCategory:
            result = _make_failed_result(
                [AcquisitionMode.UNAUTHENTICATED],
                error="test error",
                category=cat,
            )
            # Force category since _make_failed_result uses classify_failure
            result.attempts[0].failure_category = cat
            d = build_diagnostics_dict(result)
            assert d["operator_guidance"], f"No guidance for {cat.value}"

    def test_wait_seconds_in_fallback(self):
        result = _make_failed_result([AcquisitionMode.UNAUTHENTICATED])
        result.attempts[0].failure_category = FailureCategory.RATE_LIMITED
        decision = _make_decision(
            route=FallbackRoute.WAIT_RETRY_THIS_HOST,
            reason="Rate-limited — backing off.",
            category=FailureCategory.RATE_LIMITED,
            wait_seconds=30,
        )
        d = build_diagnostics_dict(result, decision)
        assert d["fallback"]["wait_seconds"] == 30

    def test_dict_is_json_serialisable(self):
        """The dict must be JSON-serialisable (no enums, datetimes, etc.)."""
        import json

        result = _make_failed_result(
            [AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE],
        )
        decision = _make_decision()
        d = build_diagnostics_dict(result, decision)
        # Should not raise
        serialised = json.dumps(d)
        assert isinstance(serialised, str)


# ---------------------------------------------------------------------------
# format_operator_summary
# ---------------------------------------------------------------------------

class TestFormatOperatorSummary:
    def test_success_summary(self):
        result = _make_success_result()
        text = format_operator_summary(result)

        assert "OK" in text
        assert "1 attempt(s)" in text
        assert "unauthenticated" in text

    def test_failed_summary_with_decision(self):
        result = _make_failed_result(
            [AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE],
        )
        decision = _make_decision()
        text = format_operator_summary(result, decision)

        assert "FAILED" in text
        assert "2 attempt(s)" in text
        assert "auth_required" in text
        assert "manual_fallback" in text
        assert decision.reason in text
        assert "Guidance:" in text

    def test_failed_summary_without_decision(self):
        result = _make_failed_result([AcquisitionMode.UNAUTHENTICATED])
        text = format_operator_summary(result)

        assert "FAILED" in text
        assert "Decision:" not in text
        assert "Guidance:" in text

    def test_wait_shown_when_nonzero(self):
        result = _make_failed_result([AcquisitionMode.UNAUTHENTICATED])
        result.attempts[0].failure_category = FailureCategory.RATE_LIMITED
        decision = _make_decision(
            route=FallbackRoute.WAIT_RETRY_THIS_HOST,
            reason="Rate-limited.",
            category=FailureCategory.RATE_LIMITED,
            wait_seconds=30,
        )
        text = format_operator_summary(result, decision)
        assert "Wait: 30s" in text

    def test_long_error_truncated(self):
        long_error = "x" * 200
        result = _make_failed_result(
            [AcquisitionMode.UNAUTHENTICATED],
            error=long_error,
            category=FailureCategory.UNKNOWN,
        )
        result.attempts[0].failure_category = FailureCategory.UNKNOWN
        result.attempts[0].error_message = long_error
        text = format_operator_summary(result)
        # Error should be truncated, not the full 200 chars
        assert "..." in text

    def test_attempt_lines_numbered(self):
        result = _make_failed_result(
            [AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE],
        )
        text = format_operator_summary(result)
        assert "  1." in text
        assert "  2." in text
