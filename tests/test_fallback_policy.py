"""Tests for the H3 fallback decision policy layer."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models.acquisition import (
    AcquisitionAttempt,
    AcquisitionMode,
    FailureCategory,
    FallbackAction,
)
from src.services.acquisition_service import AcquisitionResult
from src.services.fallback_policy import (
    FallbackDecision,
    FallbackRoute,
    decide,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    *,
    success: bool = False,
    attempts: list[AcquisitionAttempt] | None = None,
    final_action: FallbackAction | None = None,
) -> AcquisitionResult:
    return AcquisitionResult(
        success=success,
        attempts=attempts or [],
        final_action=final_action,
    )


def _failed_attempt(
    mode: AcquisitionMode = AcquisitionMode.UNAUTHENTICATED,
    category: FailureCategory = FailureCategory.UNKNOWN,
    error: str = "some error",
) -> AcquisitionAttempt:
    a = AcquisitionAttempt(mode=mode)
    a.success = False
    a.error_message = error
    a.failure_category = category
    a.finished_at = "2026-01-01T00:00:00"
    return a


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestDecideEdgeCases:
    def test_success_result_returns_abort_no_fallback(self):
        result = _make_result(success=True)
        decision = decide(result)
        assert decision.route == FallbackRoute.ABORT
        assert "succeeded" in decision.reason.lower()

    def test_no_attempts_returns_retry(self):
        result = _make_result(success=False, attempts=[])
        decision = decide(result)
        assert decision.route == FallbackRoute.RETRY_THIS_HOST
        assert decision.retry_mode == AcquisitionMode.UNAUTHENTICATED

    def test_unclassified_failure_aborts(self):
        """Attempt with no failure_category → abort."""
        a = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
        a.success = False
        a.error_message = "something"
        a.failure_category = None
        result = _make_result(attempts=[a])
        decision = decide(result)
        assert decision.route == FallbackRoute.ABORT


# ---------------------------------------------------------------------------
# AUTH_REQUIRED
# ---------------------------------------------------------------------------

class TestAuthRequired:
    @patch("src.services.fallback_policy.auth_configured", return_value=True)
    @patch.dict("os.environ", {"YT_DLP_COOKIES_FILE": "/tmp/cookies.txt"})
    def test_auth_available_not_tried_escalates(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(
                mode=AcquisitionMode.UNAUTHENTICATED,
                category=FailureCategory.AUTH_REQUIRED,
            ),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.ESCALATE_AUTH_THIS_HOST
        assert decision.retry_mode == AcquisitionMode.COOKIE_FILE
        assert "escalat" in decision.reason.lower()

    @patch("src.services.fallback_policy.auth_configured", return_value=True)
    def test_auth_tried_and_failed_manual_fallback(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(mode=AcquisitionMode.UNAUTHENTICATED, category=FailureCategory.AUTH_REQUIRED),
            _failed_attempt(mode=AcquisitionMode.COOKIE_FILE, category=FailureCategory.AUTH_REQUIRED),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.MANUAL_FALLBACK
        assert "tried" in decision.reason.lower() or "failed" in decision.reason.lower()

    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_no_auth_configured_manual_fallback(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(mode=AcquisitionMode.UNAUTHENTICATED, category=FailureCategory.AUTH_REQUIRED),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.MANUAL_FALLBACK
        assert "cookie" in decision.reason.lower() or "yt_dlp" in decision.reason.lower()


# ---------------------------------------------------------------------------
# TRANSIENT
# ---------------------------------------------------------------------------

class TestTransient:
    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_first_transient_retries_this_host(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.TRANSIENT),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.RETRY_THIS_HOST
        assert decision.retry_mode == AcquisitionMode.UNAUTHENTICATED

    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_repeated_transient_manual_fallback(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.TRANSIENT),
            _failed_attempt(category=FailureCategory.TRANSIENT),
            _failed_attempt(category=FailureCategory.TRANSIENT),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.MANUAL_FALLBACK


# ---------------------------------------------------------------------------
# RATE_LIMITED
# ---------------------------------------------------------------------------

class TestRateLimited:
    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_first_rate_limit_waits(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.RATE_LIMITED),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.WAIT_RETRY_THIS_HOST
        assert decision.wait_seconds > 0

    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_repeated_rate_limit_manual_fallback(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.RATE_LIMITED),
            _failed_attempt(category=FailureCategory.RATE_LIMITED),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.MANUAL_FALLBACK


# ---------------------------------------------------------------------------
# GEO_BLOCKED
# ---------------------------------------------------------------------------

class TestGeoBlocked:
    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_geo_blocked_manual_fallback(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.GEO_BLOCKED),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.MANUAL_FALLBACK
        assert "geo" in decision.reason.lower()


# ---------------------------------------------------------------------------
# UNAVAILABLE
# ---------------------------------------------------------------------------

class TestUnavailable:
    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_unavailable_aborts(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.UNAVAILABLE),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.ABORT
        assert "unavailable" in decision.reason.lower()


# ---------------------------------------------------------------------------
# FORMAT_ERROR
# ---------------------------------------------------------------------------

class TestFormatError:
    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_format_error_manual_fallback(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.FORMAT_ERROR),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.MANUAL_FALLBACK
        assert "format" in decision.reason.lower()


# ---------------------------------------------------------------------------
# UNKNOWN
# ---------------------------------------------------------------------------

class TestUnknown:
    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_unknown_manual_fallback(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.UNKNOWN),
        ])
        decision = decide(result)
        assert decision.route == FallbackRoute.MANUAL_FALLBACK
        assert "operator" in decision.reason.lower()


# ---------------------------------------------------------------------------
# Decision object structure
# ---------------------------------------------------------------------------

class TestDecisionStructure:
    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_exhausted_modes_tracked(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(mode=AcquisitionMode.UNAUTHENTICATED, category=FailureCategory.TRANSIENT),
        ])
        decision = decide(result)
        assert AcquisitionMode.UNAUTHENTICATED in decision.exhausted_modes

    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_failure_category_propagated(self, _mock_auth):
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.GEO_BLOCKED),
        ])
        decision = decide(result)
        assert decision.failure_category == FailureCategory.GEO_BLOCKED

    def test_decision_is_frozen(self):
        d = FallbackDecision(route=FallbackRoute.ABORT, reason="test")
        with pytest.raises(AttributeError):
            d.route = FallbackRoute.RETRY_THIS_HOST  # type: ignore[misc]

    def test_route_enum_values_stable(self):
        """Enum values are strings for serialisation stability."""
        for member in FallbackRoute:
            assert isinstance(member.value, str)


# ---------------------------------------------------------------------------
# Preference order validation
# ---------------------------------------------------------------------------

class TestPreferenceOrder:
    """Verify the policy respects: this-host retries first, then manual operator path."""

    @patch("src.services.fallback_policy.auth_configured", return_value=True)
    @patch.dict("os.environ", {"YT_DLP_COOKIES_FILE": "/tmp/c.txt"})
    def test_auth_required_tries_this_host_before_manual(self, _mock_auth):
        """First attempt at auth_required with auth available → stay on this host."""
        result = _make_result(attempts=[
            _failed_attempt(mode=AcquisitionMode.UNAUTHENTICATED, category=FailureCategory.AUTH_REQUIRED),
        ])
        d = decide(result)
        assert d.route == FallbackRoute.ESCALATE_AUTH_THIS_HOST

    @patch("src.services.fallback_policy.auth_configured", return_value=True)
    def test_auth_required_exhausted_manual_fallback(self, _mock_auth):
        """After auth tried and failed → manual fallback (no remote delegation)."""
        result = _make_result(attempts=[
            _failed_attempt(mode=AcquisitionMode.UNAUTHENTICATED, category=FailureCategory.AUTH_REQUIRED),
            _failed_attempt(mode=AcquisitionMode.COOKIE_FILE, category=FailureCategory.AUTH_REQUIRED),
        ])
        d = decide(result)
        assert d.route == FallbackRoute.MANUAL_FALLBACK

    @patch("src.services.fallback_policy.auth_configured", return_value=False)
    def test_transient_exhausted_manual_fallback(self, _mock_auth):
        """After 3 transient failures → manual fallback."""
        result = _make_result(attempts=[
            _failed_attempt(category=FailureCategory.TRANSIENT),
            _failed_attempt(category=FailureCategory.TRANSIENT),
            _failed_attempt(category=FailureCategory.TRANSIENT),
        ])
        d = decide(result)
        assert d.route == FallbackRoute.MANUAL_FALLBACK
