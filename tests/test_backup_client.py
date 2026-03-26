"""Tests for the A-side backup client (H7c).

Covers: configuration checks, successful delegation, HTTP error handling,
malformed response handling, and the is_delegation_available helper.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from src.integrations.backup_client import (
    BACKUP_SERVICE_URL_ENV,
    BackupClientError,
    delegate_transcription,
    get_backup_service_url,
    is_delegation_available,
)
from src.integrations.backup_auth import BACKUP_TOKEN_ENV
from src.integrations.backup_service import (
    DelegationRequest,
    DelegationResponse,
    DelegationResult,
    DelegationStatus,
)
from src.models.acquisition import FailureCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start each test with a clean environment."""
    monkeypatch.delenv(BACKUP_SERVICE_URL_ENV, raising=False)
    monkeypatch.delenv(BACKUP_TOKEN_ENV, raising=False)


def _sample_request() -> DelegationRequest:
    return DelegationRequest(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        language="en",
        skip_correction=False,
        originator="test-host",
        delegation_reason="geo blocked",
        job_id="job-123",
    )


def _success_response_dict() -> dict:
    return DelegationResponse(
        status=DelegationStatus.SUCCESS,
        remote_host="backup-01",
        result=DelegationResult(
            video_id="dQw4w9WgXcQ",
            title="Test Video",
            channel="Test Channel",
            duration=120,
            original_text="hello world",
            corrected_text="Hello, world.",
            language="en",
        ),
    ).to_dict()


def _failed_response_dict() -> dict:
    return DelegationResponse(
        status=DelegationStatus.FAILED,
        remote_host="backup-01",
        error_message="acquisition failed on backup",
        failure_category=FailureCategory.GEO_BLOCKED,
    ).to_dict()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_url_not_set(self):
        assert get_backup_service_url() is None

    def test_url_from_env(self, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        assert get_backup_service_url() == "http://backup:8000"

    def test_url_strips_trailing_slash(self, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000/")
        assert get_backup_service_url() == "http://backup:8000"

    def test_is_delegation_available_false_no_config(self):
        assert is_delegation_available() is False

    def test_is_delegation_available_false_url_only(self, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        assert is_delegation_available() is False

    def test_is_delegation_available_false_token_only(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")
        assert is_delegation_available() is False

    def test_is_delegation_available_true(self, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")
        assert is_delegation_available() is True


# ---------------------------------------------------------------------------
# Missing config errors
# ---------------------------------------------------------------------------

class TestMissingConfig:
    def test_no_url_raises(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")
        with pytest.raises(BackupClientError, match="URL not configured"):
            delegate_transcription(_sample_request())

    def test_no_token_raises(self, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        with pytest.raises(BackupClientError, match="token not configured"):
            delegate_transcription(_sample_request())


# ---------------------------------------------------------------------------
# Successful delegation
# ---------------------------------------------------------------------------

class TestSuccessfulDelegation:
    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_success_returns_delegation_response(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")

        resp_body = json.dumps(_success_response_dict()).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = delegate_transcription(_sample_request())

        assert isinstance(result, DelegationResponse)
        assert result.success is True
        assert result.result.video_id == "dQw4w9WgXcQ"
        assert result.result.corrected_text == "Hello, world."
        assert result.remote_host == "backup-01"

    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_request_body_contains_fields(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")

        resp_body = json.dumps(_success_response_dict()).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        delegate_transcription(_sample_request())

        # Inspect the Request object passed to urlopen
        call_args = mock_urlopen.call_args
        http_req = call_args[0][0]
        sent_body = json.loads(http_req.data.decode())
        assert sent_body["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert sent_body["language"] == "en"
        assert sent_body["originator"] == "test-host"
        assert sent_body["job_id"] == "job-123"

    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_auth_header_sent(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "my-token")

        resp_body = json.dumps(_success_response_dict()).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        delegate_transcription(_sample_request())

        http_req = mock_urlopen.call_args[0][0]
        assert http_req.get_header("Authorization") == "Bearer my-token"

    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_failed_response_parsed(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")

        resp_body = json.dumps(_failed_response_dict()).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = delegate_transcription(_sample_request())

        assert result.success is False
        assert result.status == DelegationStatus.FAILED
        assert result.failure_category == FailureCategory.GEO_BLOCKED


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_http_error_raises(self, mock_urlopen, monkeypatch):
        import urllib.error
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")

        exc = urllib.error.HTTPError(
            url="http://backup:8000/delegate/transcribe",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )
        exc.read = MagicMock(return_value=b"Invalid token")
        mock_urlopen.side_effect = exc

        with pytest.raises(BackupClientError, match="HTTP 401"):
            delegate_transcription(_sample_request())

    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_connection_refused_raises(self, mock_urlopen, monkeypatch):
        import urllib.error
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with pytest.raises(BackupClientError, match="Cannot reach"):
            delegate_transcription(_sample_request())

    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_malformed_json_raises(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv(BACKUP_SERVICE_URL_ENV, "http://backup:8000")
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not valid json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with pytest.raises(BackupClientError, match="Malformed response"):
            delegate_transcription(_sample_request())

    @patch("src.integrations.backup_client.urllib.request.urlopen")
    def test_override_url_and_token(self, mock_urlopen, monkeypatch):
        """base_url and token overrides work without env vars."""
        resp_body = json.dumps(_success_response_dict()).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = delegate_transcription(
            _sample_request(),
            base_url="http://custom:9000",
            token="custom-token",
        )
        assert result.success is True
        http_req = mock_urlopen.call_args[0][0]
        assert "custom:9000" in http_req.full_url
        assert http_req.get_header("Authorization") == "Bearer custom-token"
