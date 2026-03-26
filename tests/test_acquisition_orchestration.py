"""Integration tests for H5 acquisition orchestration glue.

Verifies that TranscriptionService wires H2 (acquisition service),
H3 (fallback policy), and H4 (alternate-host contract) together
correctly without hitting real YouTube or Whisper APIs.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.models.acquisition import (
    AcquisitionMode,
    FailureCategory,
)
from src.services.acquisition_service import AcquisitionResult
from src.services.fallback_policy import FallbackRoute
from src.services.transcription_service import (
    AcquisitionError,
    AcquisitionOutcome,
    TranscriptionService,
)
from src.youtube_extractor import VideoInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video_info(**overrides) -> VideoInfo:
    defaults = dict(
        video_id="test123",
        title="Test Video",
        description="desc",
        duration=120,
        upload_date="20240101",
        channel="TestChannel",
        channel_id="UC_test",
        view_count=1000,
        thumbnail_url="https://img.youtube.com/test.jpg",
        audio_file="/tmp/test123.mp3",
    )
    defaults.update(overrides)
    return VideoInfo(**defaults)


def _make_success_result(video_info: VideoInfo | None = None) -> AcquisitionResult:
    from src.models.acquisition import AcquisitionAttempt

    vi = video_info or _make_video_info()
    attempt = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
    attempt.record_success()
    return AcquisitionResult(
        video_info=vi,
        success=True,
        attempts=[attempt],
    )


def _make_failure_result(error_msg: str = "Sign in to confirm your age") -> AcquisitionResult:
    from src.models.acquisition import AcquisitionAttempt

    attempt = AcquisitionAttempt(mode=AcquisitionMode.UNAUTHENTICATED)
    attempt.record_failure(error_msg)
    return AcquisitionResult(
        video_info=None,
        success=False,
        attempts=[attempt],
    )


# ---------------------------------------------------------------------------
# acquire_only: success path
# ---------------------------------------------------------------------------

class TestAcquireOnlySuccess:
    def test_success_returns_video_info(self):
        svc = TranscriptionService()
        vi = _make_video_info()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_success_result(vi),
        )

        outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        assert outcome.success is True
        assert outcome.video_info is vi
        assert outcome.fallback_decision is None
        assert outcome.alternate_host_request is None
        assert outcome.diagnostics["success"] is True

    def test_success_records_diagnostics(self):
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_success_result(),
        )

        outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        assert outcome.diagnostics["strategies_tried"] == 1
        assert outcome.diagnostics["attempts"][0]["success"] is True


# ---------------------------------------------------------------------------
# acquire_only: failure → fallback decision
# ---------------------------------------------------------------------------

class TestAcquireOnlyFailure:
    def test_auth_required_no_auth_delegates_to_alternate_host(self):
        """When auth is required but not configured, H3 should recommend
        alternate-host delegation, and H5 should build the H4 request."""
        svc = TranscriptionService(originator="test-host")
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Sign in to confirm your age"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        assert outcome.success is False
        assert outcome.fallback_decision is not None
        assert outcome.fallback_decision.route == FallbackRoute.DELEGATE_ALTERNATE_HOST
        assert outcome.alternate_host_request is not None
        assert outcome.alternate_host_request.url == "https://www.youtube.com/watch?v=test123"
        assert outcome.alternate_host_request.originator == "test-host"
        assert outcome.alternate_host_request.failure_context is not None

    def test_geo_blocked_delegates_to_alternate_host(self):
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Video not available in your country"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        assert outcome.success is False
        assert outcome.fallback_decision.route == FallbackRoute.DELEGATE_ALTERNATE_HOST
        assert outcome.alternate_host_request is not None
        assert outcome.fallback_decision.failure_category == FailureCategory.GEO_BLOCKED

    def test_unavailable_aborts_no_alternate_request(self):
        """Unavailable videos should ABORT — no point delegating."""
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Video unavailable"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        assert outcome.success is False
        assert outcome.fallback_decision.route == FallbackRoute.ABORT
        assert outcome.alternate_host_request is None

    def test_format_error_manual_fallback_no_alternate_request(self):
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Requested format not available"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        assert outcome.success is False
        assert outcome.fallback_decision.route == FallbackRoute.MANUAL_FALLBACK
        assert outcome.alternate_host_request is None

    def test_failure_diagnostics_populated(self):
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Sign in to confirm your age"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        assert outcome.diagnostics["success"] is False
        assert len(outcome.diagnostics["attempts"]) == 1
        assert outcome.diagnostics["attempts"][0]["failure_category"] == "auth_required"


# ---------------------------------------------------------------------------
# run(): success path stays intact
# ---------------------------------------------------------------------------

class TestRunSuccessPath:
    @patch("src.services.transcription_service.TranscriptionService._run_short_video")
    def test_run_success_delegates_to_short_video(self, mock_short):
        """When acquisition succeeds, run() should continue to transcription."""
        svc = TranscriptionService()
        vi = _make_video_info(duration=120)
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_success_result(vi),
        )

        mock_artifacts = MagicMock()
        mock_short.return_value = mock_artifacts

        # Patch os.path.exists and os.remove to avoid file cleanup issues
        with patch("os.path.exists", return_value=False):
            result = svc.run("https://www.youtube.com/watch?v=test123", skip_correction=True)

        assert result is mock_artifacts
        mock_short.assert_called_once()
        call_kwargs = mock_short.call_args
        assert call_kwargs[1]["video_info"] is vi


# ---------------------------------------------------------------------------
# run(): failure path raises AcquisitionError
# ---------------------------------------------------------------------------

class TestRunFailurePath:
    def test_run_failure_raises_acquisition_error(self):
        """When acquisition fails, run() should raise AcquisitionError
        with structured diagnostics attached."""
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Sign in to confirm your age"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            with pytest.raises(AcquisitionError) as exc_info:
                svc.run("https://www.youtube.com/watch?v=test123")

        err = exc_info.value
        assert err.acquisition_result is not None
        assert err.fallback_decision is not None
        assert err.fallback_decision.route == FallbackRoute.DELEGATE_ALTERNATE_HOST
        assert err.alternate_host_request is not None
        assert "Sign in" not in str(err)  # raw error shouldn't leak as the message
        assert "Acquisition failed" in str(err)

    def test_run_failure_abort_no_alternate_request(self):
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Video unavailable"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            with pytest.raises(AcquisitionError) as exc_info:
                svc.run("https://www.youtube.com/watch?v=test123")

        err = exc_info.value
        assert err.fallback_decision.route == FallbackRoute.ABORT
        assert err.alternate_host_request is None


# ---------------------------------------------------------------------------
# H4 request construction from orchestration
# ---------------------------------------------------------------------------

class TestAlternateHostRequestConstruction:
    def test_request_carries_failure_context(self):
        svc = TranscriptionService(originator="node-01")
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Sign in to confirm your age"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        req = outcome.alternate_host_request
        assert req is not None
        assert req.originator == "node-01"
        assert req.failure_context is not None
        assert req.failure_context.last_category == FailureCategory.AUTH_REQUIRED
        assert AcquisitionMode.UNAUTHENTICATED in req.failure_context.exhausted_modes

    def test_request_serializes_to_json(self):
        """The H4 request should be JSON-serializable for wire transport."""
        svc = TranscriptionService(originator="node-01")
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Not available in your country"),
        )

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            outcome = svc.acquire_only("https://www.youtube.com/watch?v=test123")

        req = outcome.alternate_host_request
        json_str = req.to_json()
        assert '"url"' in json_str
        assert "test123" in json_str


# ---------------------------------------------------------------------------
# Progress callback integration
# ---------------------------------------------------------------------------

class TestProgressCallbacks:
    def test_success_emits_downloading_progress(self):
        svc = TranscriptionService()
        vi = _make_video_info()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_success_result(vi),
        )

        progress_calls = []

        def track_progress(status, pct, msg):
            progress_calls.append((status, pct, msg))

        # Use acquire_only-like approach but with progress tracking
        from src.models.job import JobStatus
        svc._acquire("https://www.youtube.com/watch?v=test123", track_progress)

        statuses = [s for s, _, _ in progress_calls]
        assert JobStatus.DOWNLOADING in statuses
        assert len(progress_calls) >= 2  # initial + completion

    def test_failure_emits_downloading_progress(self):
        svc = TranscriptionService()
        svc.acquisition_service.acquire = MagicMock(
            return_value=_make_failure_result("Sign in to confirm"),
        )

        progress_calls = []

        def track_progress(status, pct, msg):
            progress_calls.append((status, pct, msg))

        with patch("src.services.fallback_policy.auth_configured", return_value=False):
            svc._acquire("https://www.youtube.com/watch?v=test123", track_progress)

        assert len(progress_calls) >= 1  # at least the initial progress


# ---------------------------------------------------------------------------
# Existing URL validation still works
# ---------------------------------------------------------------------------

class TestUrlValidationUnchanged:
    def test_valid_urls(self):
        svc = TranscriptionService()
        assert svc.validate_url("https://www.youtube.com/watch?v=abc123") is True
        assert svc.validate_url("https://youtu.be/abc123") is True

    def test_invalid_urls(self):
        svc = TranscriptionService()
        assert svc.validate_url("https://example.com") is False
        assert svc.validate_url("not-a-url") is False
