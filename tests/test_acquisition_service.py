"""Tests for this-host acquisition service — strategy selection & diagnostics (Unit H2)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.models.acquisition import (
    AcquisitionMode,
    FailureCategory,
    FallbackAction,
)
from src.services.acquisition_service import (
    AcquisitionResult,
    ThisHostAcquisitionService,
    auth_configured,
    build_strategy_order,
)
from src.youtube_extractor import YouTubeExtractor, VideoInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video_info(**overrides) -> VideoInfo:
    defaults = dict(
        video_id="abc123",
        title="Test Video",
        description="desc",
        duration=120,
        upload_date="20260101",
        channel="TestCh",
        channel_id="UC123",
        view_count=999,
        thumbnail_url="https://example.com/thumb.jpg",
        audio_file="/tmp/abc123.mp3",
    )
    defaults.update(overrides)
    return VideoInfo(**defaults)


# ---------------------------------------------------------------------------
# build_strategy_order
# ---------------------------------------------------------------------------


class TestBuildStrategyOrder:
    """Strategy order depends on auth env vars and auth_first flag."""

    def test_no_auth_returns_unauthenticated_only(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)
        assert build_strategy_order() == [AcquisitionMode.UNAUTHENTICATED]

    def test_cookie_file_default_order(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)
        order = build_strategy_order()
        assert order == [AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE]

    def test_cookie_browser_default_order(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.setenv("YT_DLP_COOKIES_FROM_BROWSER", "firefox")
        order = build_strategy_order()
        assert order == [AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_BROWSER]

    def test_cookie_file_takes_precedence(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")
        monkeypatch.setenv("YT_DLP_COOKIES_FROM_BROWSER", "firefox")
        order = build_strategy_order()
        assert order[1] == AcquisitionMode.COOKIE_FILE

    def test_auth_first_reverses_order(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)
        order = build_strategy_order(auth_first=True)
        assert order == [AcquisitionMode.COOKIE_FILE, AcquisitionMode.UNAUTHENTICATED]

    def test_auth_first_no_auth_still_unauthenticated(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)
        assert build_strategy_order(auth_first=True) == [AcquisitionMode.UNAUTHENTICATED]


# ---------------------------------------------------------------------------
# auth_configured
# ---------------------------------------------------------------------------


class TestAuthConfigured:
    def test_false_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)
        assert auth_configured() is False

    def test_true_with_cookie_file(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")
        assert auth_configured() is True

    def test_true_with_cookie_browser(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.setenv("YT_DLP_COOKIES_FROM_BROWSER", "chrome")
        assert auth_configured() is True


# ---------------------------------------------------------------------------
# ThisHostAcquisitionService — success on first strategy
# ---------------------------------------------------------------------------


class TestAcquireSuccess:
    """When the first strategy succeeds, no further strategies are tried."""

    def test_success_on_first_attempt(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor)

        expected_info = _make_video_info()
        with patch.object(svc, "_run_extraction", return_value=expected_info):
            result = svc.acquire("https://youtube.com/watch?v=abc123")

        assert result.success is True
        assert result.video_info is expected_info
        assert result.strategy_count == 1
        assert result.attempts[0].mode == AcquisitionMode.UNAUTHENTICATED
        assert result.attempts[0].success is True
        assert result.final_action is None

    def test_success_on_second_attempt_after_auth_error(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor)

        expected_info = _make_video_info()
        call_count = 0

        def fake_extract(url, mode, *, download, format, quality):
            nonlocal call_count
            call_count += 1
            if mode == AcquisitionMode.UNAUTHENTICATED:
                raise Exception("Sign in to confirm you're not a bot")
            return expected_info

        with patch.object(svc, "_run_extraction", side_effect=fake_extract):
            result = svc.acquire("https://youtube.com/watch?v=abc123")

        assert result.success is True
        assert result.strategy_count == 2
        assert result.attempts[0].mode == AcquisitionMode.UNAUTHENTICATED
        assert result.attempts[0].success is False
        assert result.attempts[0].failure_category == FailureCategory.AUTH_REQUIRED
        assert result.attempts[1].mode == AcquisitionMode.COOKIE_FILE
        assert result.attempts[1].success is True


# ---------------------------------------------------------------------------
# ThisHostAcquisitionService — all strategies fail
# ---------------------------------------------------------------------------


class TestAcquireAllFail:
    """When all strategies fail, result has diagnostics and final_action."""

    def test_single_strategy_fails(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor)

        with patch.object(
            svc,
            "_run_extraction",
            side_effect=Exception("Sign in to confirm you're not a bot"),
        ):
            result = svc.acquire("https://youtube.com/watch?v=abc123")

        assert result.success is False
        assert result.video_info is None
        assert result.strategy_count == 1
        assert result.last_failure_category == FailureCategory.AUTH_REQUIRED
        # No auth configured → ESCALATE_AUTH
        assert result.final_action == FallbackAction.ESCALATE_AUTH

    def test_both_strategies_fail(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor)

        with patch.object(
            svc,
            "_run_extraction",
            side_effect=Exception("Sign in to confirm you're not a bot"),
        ):
            result = svc.acquire("https://youtube.com/watch?v=abc123")

        assert result.success is False
        assert result.strategy_count == 2
        # Auth IS configured but still failed → ABORT
        assert result.final_action == FallbackAction.ABORT

    def test_transient_failure_suggests_retry(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor)

        with patch.object(
            svc,
            "_run_extraction",
            side_effect=Exception("Connection timed out"),
        ):
            result = svc.acquire("https://youtube.com/watch?v=abc123")

        assert result.success is False
        assert result.last_failure_category == FailureCategory.TRANSIENT
        assert result.final_action == FallbackAction.RETRY_SAME_MODE

    def test_unavailable_aborts(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor)

        with patch.object(
            svc,
            "_run_extraction",
            side_effect=Exception("Video unavailable"),
        ):
            result = svc.acquire("https://youtube.com/watch?v=abc123")

        assert result.success is False
        assert result.last_failure_category == FailureCategory.UNAVAILABLE
        assert result.final_action == FallbackAction.ABORT


# ---------------------------------------------------------------------------
# AcquisitionResult — diagnostics output
# ---------------------------------------------------------------------------


class TestDiagnostics:
    """diagnostics() returns a serialisable dict with all attempt details."""

    def test_success_diagnostics(self):
        from src.models.acquisition import AcquisitionAttempt

        attempt = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
        attempt.record_success()

        result = AcquisitionResult(
            video_info=_make_video_info(),
            success=True,
            attempts=[attempt],
        )

        diag = result.diagnostics()
        assert diag["success"] is True
        assert diag["strategies_tried"] == 1
        assert len(diag["attempts"]) == 1
        assert diag["attempts"][0]["mode"] == "unauthenticated"
        assert diag["attempts"][0]["success"] is True
        assert diag["attempts"][0]["failure_category"] is None
        assert diag["final_action"] is None

    def test_failure_diagnostics(self):
        from src.models.acquisition import AcquisitionAttempt

        a1 = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
        a1.record_failure("Sign in to confirm you're not a bot")

        a2 = AcquisitionAttempt(mode=AcquisitionMode.COOKIE_FILE)
        a2.record_failure("Sign in to confirm you're not a bot")

        result = AcquisitionResult(
            success=False,
            attempts=[a1, a2],
            final_action=FallbackAction.ABORT,
        )

        diag = result.diagnostics()
        assert diag["success"] is False
        assert diag["strategies_tried"] == 2
        assert diag["attempts"][0]["failure_category"] == "auth_required"
        assert diag["attempts"][1]["failure_category"] == "auth_required"
        assert diag["final_action"] == "abort"

    def test_last_failure_category_skips_success(self):
        from src.models.acquisition import AcquisitionAttempt

        a1 = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
        a1.record_failure("Connection timed out")

        a2 = AcquisitionAttempt(mode=AcquisitionMode.COOKIE_FILE)
        a2.record_success()

        result = AcquisitionResult(success=True, attempts=[a1, a2])
        # Last failure is from a1 (transient), but a2 succeeded
        assert result.last_failure_category == FailureCategory.TRANSIENT


# ---------------------------------------------------------------------------
# auth_first mode
# ---------------------------------------------------------------------------


class TestAuthFirstMode:
    """When auth_first=True, authenticated strategy runs before unauthenticated."""

    def test_auth_first_tries_auth_mode_first(self, monkeypatch):
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor, auth_first=True)

        expected_info = _make_video_info()
        with patch.object(svc, "_run_extraction", return_value=expected_info):
            result = svc.acquire("https://youtube.com/watch?v=abc123")

        assert result.success is True
        assert result.strategy_count == 1
        assert result.attempts[0].mode == AcquisitionMode.COOKIE_FILE


# ---------------------------------------------------------------------------
# Extract-info-only mode (download=False)
# ---------------------------------------------------------------------------


class TestExtractInfoOnly:
    def test_acquire_info_only(self, monkeypatch):
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)

        extractor = YouTubeExtractor(output_dir="/tmp")
        svc = ThisHostAcquisitionService(extractor)

        expected_info = _make_video_info(audio_file=None)
        with patch.object(svc, "_run_extraction", return_value=expected_info):
            result = svc.acquire(
                "https://youtube.com/watch?v=abc123", download=False
            )

        assert result.success is True
        assert result.video_info is expected_info
