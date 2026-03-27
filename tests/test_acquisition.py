"""Tests for acquisition mode, failure classification, and fallback hints (Unit H1)."""

import pytest

from src.models.acquisition import (
    AcquisitionAttempt,
    AcquisitionMode,
    FailureCategory,
    FallbackAction,
    classify_failure,
    is_retryable,
    suggest_fallback,
)


# ---------------------------------------------------------------------------
# classify_failure – deterministic mapping of error strings → categories
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    """Each real-world yt-dlp error message must map to the expected bucket."""

    @pytest.mark.parametrize("msg, expected", [
        # AUTH_REQUIRED – bot / sign-in gate
        ("Sign in to confirm you're not a bot", FailureCategory.AUTH_REQUIRED),
        ("ERROR: Sign in to confirm your age", FailureCategory.AUTH_REQUIRED),
        ("Please sign in to continue", FailureCategory.AUTH_REQUIRED),
        ("login required", FailureCategory.AUTH_REQUIRED),
        ("Use --cookies or --cookies-from-browser", FailureCategory.AUTH_REQUIRED),
        ("bot detection: please verify", FailureCategory.AUTH_REQUIRED),
        ("age-restricted video", FailureCategory.AUTH_REQUIRED),
        ("captcha required", FailureCategory.AUTH_REQUIRED),
        ("consent page detected", FailureCategory.AUTH_REQUIRED),
        ("cookies from browser to authenticate", FailureCategory.AUTH_REQUIRED),

        # TRANSIENT – reload / network
        ("The page needs to be reloaded", FailureCategory.TRANSIENT),
        ("Network error: connection reset", FailureCategory.TRANSIENT),
        ("Connection timed out", FailureCategory.TRANSIENT),
        ("Read timed out", FailureCategory.TRANSIENT),
        ("HTTP Error 500: Internal Server Error", FailureCategory.TRANSIENT),
        ("HTTP Error 503: Service Unavailable", FailureCategory.TRANSIENT),
        ("server error encountered", FailureCategory.TRANSIENT),
        ("incomplete read", FailureCategory.TRANSIENT),

        # RATE_LIMITED
        ("HTTP Error 429: Too Many Requests", FailureCategory.RATE_LIMITED),
        ("too many requests", FailureCategory.RATE_LIMITED),
        ("rate-limited by server", FailureCategory.RATE_LIMITED),
        ("rate limit exceeded", FailureCategory.RATE_LIMITED),

        # GEO_BLOCKED
        ("not available in your country", FailureCategory.GEO_BLOCKED),
        ("geo-restricted content", FailureCategory.GEO_BLOCKED),
        ("This video is blocked in your region", FailureCategory.GEO_BLOCKED),

        # UNAVAILABLE – deleted / private / copyright
        ("Video unavailable", FailureCategory.UNAVAILABLE),
        ("Video is not available", FailureCategory.UNAVAILABLE),
        ("This video has been removed", FailureCategory.UNAVAILABLE),
        ("This video was removed by the uploader", FailureCategory.UNAVAILABLE),
        ("Private video", FailureCategory.UNAVAILABLE),
        ("copyright claim", FailureCategory.UNAVAILABLE),
        ("account terminated", FailureCategory.UNAVAILABLE),
        ("HTTP Error 404: Not Found", FailureCategory.UNAVAILABLE),

        # FORMAT_ERROR
        ("format not available", FailureCategory.FORMAT_ERROR),
        ("format is not available", FailureCategory.FORMAT_ERROR),
        ("no suitable format found", FailureCategory.FORMAT_ERROR),
        ("requested format not available", FailureCategory.FORMAT_ERROR),
        ("Requested format is not available. Use --list-formats for a list of available formats", FailureCategory.FORMAT_ERROR),
        ("no video formats found", FailureCategory.FORMAT_ERROR),
        ("Use --list-formats to see available formats", FailureCategory.FORMAT_ERROR),
    ])
    def test_known_patterns(self, msg: str, expected: FailureCategory):
        assert classify_failure(msg) == expected

    def test_unknown_message_returns_unknown(self):
        assert classify_failure("something completely unexpected") == FailureCategory.UNKNOWN

    def test_empty_string_returns_unknown(self):
        assert classify_failure("") == FailureCategory.UNKNOWN


# ---------------------------------------------------------------------------
# is_retryable
# ---------------------------------------------------------------------------


class TestIsRetryable:
    @pytest.mark.parametrize("cat", [
        FailureCategory.AUTH_REQUIRED,
        FailureCategory.TRANSIENT,
        FailureCategory.RATE_LIMITED,
    ])
    def test_retryable_categories(self, cat: FailureCategory):
        assert is_retryable(cat) is True

    @pytest.mark.parametrize("cat", [
        FailureCategory.GEO_BLOCKED,
        FailureCategory.UNAVAILABLE,
        FailureCategory.FORMAT_ERROR,
        FailureCategory.UNKNOWN,
    ])
    def test_non_retryable_categories(self, cat: FailureCategory):
        assert is_retryable(cat) is False


# ---------------------------------------------------------------------------
# suggest_fallback
# ---------------------------------------------------------------------------


class TestSuggestFallback:
    def test_auth_required_no_auth_configured(self):
        assert suggest_fallback(FailureCategory.AUTH_REQUIRED, auth_configured=False) == FallbackAction.ESCALATE_AUTH

    def test_auth_required_auth_already_configured(self):
        assert suggest_fallback(FailureCategory.AUTH_REQUIRED, auth_configured=True) == FallbackAction.ABORT

    def test_transient_retries_same_mode(self):
        assert suggest_fallback(FailureCategory.TRANSIENT, auth_configured=False) == FallbackAction.RETRY_SAME_MODE

    def test_rate_limited_waits(self):
        assert suggest_fallback(FailureCategory.RATE_LIMITED, auth_configured=False) == FallbackAction.WAIT_AND_RETRY

    @pytest.mark.parametrize("cat", [
        FailureCategory.GEO_BLOCKED,
        FailureCategory.UNAVAILABLE,
        FailureCategory.FORMAT_ERROR,
        FailureCategory.UNKNOWN,
    ])
    def test_non_retryable_aborts(self, cat: FailureCategory):
        assert suggest_fallback(cat, auth_configured=False) == FallbackAction.ABORT


# ---------------------------------------------------------------------------
# AcquisitionAttempt – record keeping
# ---------------------------------------------------------------------------


class TestAcquisitionAttempt:
    def test_record_success(self):
        attempt = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
        attempt.record_success()
        assert attempt.success is True
        assert attempt.finished_at is not None
        assert attempt.failure_category is None

    def test_record_failure_classifies(self):
        attempt = AcquisitionAttempt(mode=AcquisitionMode.COOKIE_FILE)
        attempt.record_failure("Sign in to confirm you're not a bot")
        assert attempt.success is False
        assert attempt.failure_category == FailureCategory.AUTH_REQUIRED
        assert attempt.error_message == "Sign in to confirm you're not a bot"
        assert attempt.finished_at is not None

    def test_record_failure_unknown(self):
        attempt = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
        attempt.record_failure("weird error nobody expected")
        assert attempt.failure_category == FailureCategory.UNKNOWN


# ---------------------------------------------------------------------------
# Enum string values – ensure stable serialisation
# ---------------------------------------------------------------------------


class TestEnumValues:
    """Guard against accidental renames that would break stored data."""

    def test_acquisition_modes(self):
        assert AcquisitionMode.UNAUTHENTICATED == "unauthenticated"
        assert AcquisitionMode.COOKIE_FILE == "cookie_file"
        assert AcquisitionMode.COOKIE_BROWSER == "cookie_browser"
        assert AcquisitionMode.OAUTH == "oauth"

    def test_failure_categories(self):
        assert FailureCategory.AUTH_REQUIRED == "auth_required"
        assert FailureCategory.TRANSIENT == "transient"
        assert FailureCategory.RATE_LIMITED == "rate_limited"
        assert FailureCategory.GEO_BLOCKED == "geo_blocked"
        assert FailureCategory.UNAVAILABLE == "unavailable"
        assert FailureCategory.FORMAT_ERROR == "format_error"
        assert FailureCategory.UNKNOWN == "unknown"

    def test_fallback_actions(self):
        assert FallbackAction.RETRY_SAME_MODE == "retry_same_mode"
        assert FallbackAction.ESCALATE_AUTH == "escalate_auth"
        assert FallbackAction.ABORT == "abort"
        assert FallbackAction.WAIT_AND_RETRY == "wait_and_retry"
