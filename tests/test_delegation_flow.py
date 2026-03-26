"""Integration tests for the H7c delegation flow.

Validates end-to-end behaviour when local acquisition fails and the
orchestrator delegates to the backup service:
  - local-fail → remote-success (delegated result returned)
  - local-fail → remote-fail (AcquisitionError raised)
  - local-fail → backup not configured (original failure preserved)
  - local-success (delegation never attempted)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.integrations.backup_client import BackupClientError
from src.integrations.backup_service import (
    DelegationResponse,
    DelegationResult,
    DelegationStatus,
)
from src.models.acquisition import AcquisitionMode, FailureCategory
from src.services.acquisition_service import AcquisitionResult
from src.services.fallback_policy import FallbackDecision, FallbackRoute
from src.services.transcription_service import (
    AcquisitionError,
    TranscriptionService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_failed_acq_result() -> AcquisitionResult:
    """Build a failed AcquisitionResult that triggers DELEGATE_ALTERNATE_HOST."""
    result = MagicMock(spec=AcquisitionResult)
    result.success = False
    result.video_info = None
    result.strategy_count = 1
    result.last_failure_category = FailureCategory.GEO_BLOCKED
    result.attempts = [
        MagicMock(
            mode=AcquisitionMode.UNAUTHENTICATED,
            success=False,
            failure_category=FailureCategory.GEO_BLOCKED,
            error_message="geo blocked",
        )
    ]
    result.diagnostics.return_value = {
        "success": False,
        "strategy_count": 1,
        "attempts": [],
    }
    return result


def _make_successful_acq_result() -> AcquisitionResult:
    """Build a successful AcquisitionResult."""
    video_info = MagicMock()
    video_info.video_id = "local123"
    video_info.title = "Local Video"
    video_info.channel = "Local Channel"
    video_info.duration = 60
    video_info.audio_file = "/tmp/fake_audio.m4a"

    result = MagicMock(spec=AcquisitionResult)
    result.success = True
    result.video_info = video_info
    result.strategy_count = 1
    result.diagnostics.return_value = {"success": True}
    return result


def _success_delegation_response() -> DelegationResponse:
    return DelegationResponse(
        status=DelegationStatus.SUCCESS,
        remote_host="backup-01",
        result=DelegationResult(
            video_id="dQw4w9WgXcQ",
            title="Remote Video",
            channel="Remote Channel",
            duration=120,
            original_text="hello world",
            corrected_text="Hello, world.",
            language="en",
        ),
    )


def _failed_delegation_response() -> DelegationResponse:
    return DelegationResponse(
        status=DelegationStatus.FAILED,
        remote_host="backup-01",
        error_message="remote acquisition also failed",
        failure_category=FailureCategory.GEO_BLOCKED,
    )


# ---------------------------------------------------------------------------
# local-fail → remote-success
# ---------------------------------------------------------------------------

class TestLocalFailRemoteSuccess:
    @patch("src.services.transcription_service.is_delegation_available", return_value=True)
    @patch("src.services.transcription_service.delegate_transcription")
    @patch("src.services.transcription_service.decide_fallback")
    @patch.object(TranscriptionService, "_run_short_video", return_value=None)
    def test_delegated_result_returned(
        self, mock_short, mock_decide, mock_delegate, mock_avail
    ):
        """When local acquisition fails and backup succeeds, run() returns
        the remote result as TranscriptArtifacts."""
        # H3 says delegate
        mock_decide.return_value = FallbackDecision(
            route=FallbackRoute.DELEGATE_ALTERNATE_HOST,
            reason="geo blocked",
            failure_category=FailureCategory.GEO_BLOCKED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,),
        )

        # Backup succeeds
        mock_delegate.return_value = _success_delegation_response()

        svc = TranscriptionService()
        svc.acquisition_service = MagicMock()
        svc.acquisition_service.acquire.return_value = _make_failed_acq_result()

        artifacts = svc.run(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            language="en",
        )

        # Result comes from delegation, not local pipeline
        assert artifacts.video_info.video_id == "dQw4w9WgXcQ"
        assert artifacts.video_info.title == "Remote Video"
        assert artifacts.original_text == "hello world"
        assert artifacts.corrected_text == "Hello, world."
        assert artifacts.language == "en"

        # Local pipeline was NOT invoked
        mock_short.assert_not_called()

    @patch("src.services.transcription_service.is_delegation_available", return_value=True)
    @patch("src.services.transcription_service.delegate_transcription")
    @patch("src.services.transcription_service.decide_fallback")
    def test_delegation_request_carries_pipeline_params(
        self, mock_decide, mock_delegate, mock_avail
    ):
        """The DelegationRequest forwarded to backup includes language,
        skip_correction, custom_terms, and job_id."""
        mock_decide.return_value = FallbackDecision(
            route=FallbackRoute.DELEGATE_ALTERNATE_HOST,
            reason="geo blocked",
            failure_category=FailureCategory.GEO_BLOCKED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,),
        )
        mock_delegate.return_value = _success_delegation_response()

        svc = TranscriptionService(originator="my-host")
        svc.acquisition_service = MagicMock()
        svc.acquisition_service.acquire.return_value = _make_failed_acq_result()

        svc.run(
            url="https://www.youtube.com/watch?v=test",
            language="zh",
            skip_correction=True,
            custom_terms=["GPT-4", "FastAPI"],
            job_id="j-42",
        )

        req = mock_delegate.call_args[0][0]
        assert req.url == "https://www.youtube.com/watch?v=test"
        assert req.language == "zh"
        assert req.skip_correction is True
        assert req.custom_terms == ("GPT-4", "FastAPI")
        assert req.job_id == "j-42"
        assert req.originator == "my-host"


# ---------------------------------------------------------------------------
# local-fail → remote-fail
# ---------------------------------------------------------------------------

class TestLocalFailRemoteFail:
    @patch("src.services.transcription_service.is_delegation_available", return_value=True)
    @patch("src.services.transcription_service.delegate_transcription")
    @patch("src.services.transcription_service.decide_fallback")
    def test_remote_failure_raises_acquisition_error(
        self, mock_decide, mock_delegate, mock_avail
    ):
        """When both local and remote fail, AcquisitionError is raised."""
        mock_decide.return_value = FallbackDecision(
            route=FallbackRoute.DELEGATE_ALTERNATE_HOST,
            reason="geo blocked",
            failure_category=FailureCategory.GEO_BLOCKED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,),
        )
        mock_delegate.return_value = _failed_delegation_response()

        svc = TranscriptionService()
        svc.acquisition_service = MagicMock()
        svc.acquisition_service.acquire.return_value = _make_failed_acq_result()

        with pytest.raises(AcquisitionError):
            svc.run(url="https://www.youtube.com/watch?v=test")

    @patch("src.services.transcription_service.is_delegation_available", return_value=True)
    @patch("src.services.transcription_service.delegate_transcription")
    @patch("src.services.transcription_service.decide_fallback")
    def test_backup_client_error_raises_acquisition_error(
        self, mock_decide, mock_delegate, mock_avail
    ):
        """When the HTTP call to backup fails, AcquisitionError is raised."""
        mock_decide.return_value = FallbackDecision(
            route=FallbackRoute.DELEGATE_ALTERNATE_HOST,
            reason="transient failure",
            failure_category=FailureCategory.TRANSIENT,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,) * 3,
        )
        mock_delegate.side_effect = BackupClientError("Connection refused")

        svc = TranscriptionService()
        svc.acquisition_service = MagicMock()
        svc.acquisition_service.acquire.return_value = _make_failed_acq_result()

        with pytest.raises(AcquisitionError):
            svc.run(url="https://www.youtube.com/watch?v=test")


# ---------------------------------------------------------------------------
# local-fail → backup not configured
# ---------------------------------------------------------------------------

class TestBackupNotConfigured:
    @patch("src.services.transcription_service.is_delegation_available", return_value=False)
    @patch("src.services.transcription_service.decide_fallback")
    def test_raises_without_attempting_delegation(
        self, mock_decide, mock_avail
    ):
        """When backup is not configured, delegation is not attempted and
        AcquisitionError is raised with the original failure."""
        mock_decide.return_value = FallbackDecision(
            route=FallbackRoute.DELEGATE_ALTERNATE_HOST,
            reason="geo blocked",
            failure_category=FailureCategory.GEO_BLOCKED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,),
        )

        svc = TranscriptionService()
        svc.acquisition_service = MagicMock()
        svc.acquisition_service.acquire.return_value = _make_failed_acq_result()

        with pytest.raises(AcquisitionError) as exc_info:
            svc.run(url="https://www.youtube.com/watch?v=test")

        assert exc_info.value.alternate_host_request is not None


# ---------------------------------------------------------------------------
# local-success (delegation never attempted)
# ---------------------------------------------------------------------------

class TestLocalSuccess:
    @patch("src.services.transcription_service.is_delegation_available", return_value=True)
    @patch("src.services.transcription_service.delegate_transcription")
    def test_delegation_not_called_on_local_success(
        self, mock_delegate, mock_avail
    ):
        """When local acquisition succeeds, the backup client is never called."""
        acq_result = _make_successful_acq_result()

        svc = TranscriptionService()
        svc.acquisition_service = MagicMock()
        svc.acquisition_service.acquire.return_value = acq_result

        # Mock the pipeline so we don't need real whisper/GPT
        with patch.object(svc, "_run_short_video") as mock_short:
            mock_short.return_value = MagicMock(
                video_info=acq_result.video_info,
                original_text="text",
                corrected_text="text",
                language="en",
            )
            # Need to also mock cleanup
            with patch("os.path.exists", return_value=False):
                svc.run(url="https://www.youtube.com/watch?v=test")

        mock_delegate.assert_not_called()
