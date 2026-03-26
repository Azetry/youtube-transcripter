"""Tests for the backup-service delegation endpoint (H7b).

Covers auth enforcement, request validation, pipeline success/failure,
and the health check sub-endpoint.
"""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.integrations.backup_auth import BACKUP_TOKEN_ENV
from src.integrations.backup_service import (
    DelegationRequest,
    DelegationResponse,
    DelegationStatus,
)
from src.models.acquisition import FailureCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _set_token(monkeypatch):
    """Ensure a valid backup token is configured for every test."""
    monkeypatch.setenv(BACKUP_TOKEN_ENV, "test-secret")


@pytest.fixture()
def client():
    """Build a TestClient around the FastAPI app."""
    from api.main import app
    return TestClient(app)


def _auth_header(token: str = "test-secret") -> dict:
    return {"Authorization": f"Bearer {token}"}


def _sample_body() -> dict:
    return DelegationRequest(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        language="en",
        skip_correction=False,
        originator="primary-host",
        delegation_reason="acquisition failure",
    ).to_dict()


def _make_artifacts():
    """Build a minimal mock TranscriptArtifacts."""
    info = MagicMock()
    info.video_id = "dQw4w9WgXcQ"
    info.title = "Test Video"
    info.channel = "Test Channel"
    info.duration = 120

    arts = MagicMock()
    arts.video_info = info
    arts.original_text = "hello world"
    arts.corrected_text = "Hello, world."
    arts.language = "en"
    arts.similarity_ratio = 0.95
    arts.change_count = 2
    arts.diff_inline = ""
    arts.is_merged = False
    return arts


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------

class TestAuth:
    def test_missing_token_returns_401(self, client):
        resp = client.post("/delegate/transcribe", json=_sample_body())
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header("wrong-token"),
        )
        assert resp.status_code == 401

    def test_empty_bearer_returns_401(self, client):
        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401

    def test_no_configured_token_rejects(self, client, monkeypatch):
        monkeypatch.delenv(BACKUP_TOKEN_ENV)
        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header("anything"),
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Request validation
# ---------------------------------------------------------------------------

class TestRequestValidation:
    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/delegate/transcribe",
            content=b"not-json",
            headers={**_auth_header(), "Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_missing_url_returns_400(self, client):
        body = _sample_body()
        del body["url"]
        resp = client.post(
            "/delegate/transcribe",
            json=body,
            headers=_auth_header(),
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Pipeline success
# ---------------------------------------------------------------------------

class TestPipelineSuccess:
    @patch("api.delegation.TranscriptionService")
    def test_successful_delegation(self, mock_svc_cls, client):
        mock_svc = MagicMock()
        mock_svc.run.return_value = _make_artifacts()
        mock_svc_cls.return_value = mock_svc

        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["delegated"] is True
        assert data["result"]["video_id"] == "dQw4w9WgXcQ"
        assert data["result"]["title"] == "Test Video"
        assert data["result"]["original_text"] == "hello world"
        assert data["result"]["corrected_text"] == "Hello, world."
        assert data["result"]["language"] == "en"
        assert data["remote_host"]  # non-empty

    @patch("api.delegation.TranscriptionService")
    def test_response_round_trips_via_model(self, mock_svc_cls, client):
        """Verify the response dict can be parsed back into DelegationResponse."""
        mock_svc = MagicMock()
        mock_svc.run.return_value = _make_artifacts()
        mock_svc_cls.return_value = mock_svc

        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header(),
        )
        parsed = DelegationResponse.from_dict(resp.json())
        assert parsed.success is True
        assert parsed.result.video_id == "dQw4w9WgXcQ"

    @patch("api.delegation.TranscriptionService")
    def test_custom_terms_forwarded(self, mock_svc_cls, client):
        mock_svc = MagicMock()
        mock_svc.run.return_value = _make_artifacts()
        mock_svc_cls.return_value = mock_svc

        body = _sample_body()
        body["custom_terms"] = ["GPT-4", "FastAPI"]
        client.post(
            "/delegate/transcribe",
            json=body,
            headers=_auth_header(),
        )
        call_kwargs = mock_svc.run.call_args
        assert call_kwargs.kwargs.get("custom_terms") == ["GPT-4", "FastAPI"]


# ---------------------------------------------------------------------------
# Pipeline failure
# ---------------------------------------------------------------------------

class TestPipelineFailure:
    @patch("api.delegation.TranscriptionService")
    def test_acquisition_error_returns_failed(self, mock_svc_cls, client):
        from src.services.transcription_service import AcquisitionError

        mock_svc = MagicMock()
        mock_svc.run.side_effect = AcquisitionError("geo blocked")
        mock_svc_cls.return_value = mock_svc

        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert "geo blocked" in data["error_message"]
        assert data["failure_category"] == "unknown"
        assert data["delegated"] is True

    @patch("api.delegation.TranscriptionService")
    def test_generic_error_returns_failed(self, mock_svc_cls, client):
        mock_svc = MagicMock()
        mock_svc.run.side_effect = RuntimeError("whisper crashed")
        mock_svc_cls.return_value = mock_svc

        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert "whisper crashed" in data["error_message"]

    @patch("api.delegation.TranscriptionService")
    def test_failure_response_round_trips(self, mock_svc_cls, client):
        mock_svc = MagicMock()
        mock_svc.run.side_effect = RuntimeError("boom")
        mock_svc_cls.return_value = mock_svc

        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header(),
        )
        parsed = DelegationResponse.from_dict(resp.json())
        assert parsed.success is False
        assert parsed.status == DelegationStatus.FAILED

    @patch("api.delegation.TranscriptionService")
    def test_rate_limit_classified(self, mock_svc_cls, client):
        mock_svc = MagicMock()
        mock_svc.run.side_effect = RuntimeError("HTTP 429 rate limited")
        mock_svc_cls.return_value = mock_svc

        resp = client.post(
            "/delegate/transcribe",
            json=_sample_body(),
            headers=_auth_header(),
        )
        data = resp.json()
        assert data["failure_category"] == "rate_limited"


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestDelegateHealth:
    def test_healthy_when_configured(self, client, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        resp = client.get("/delegate/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is True
        assert data["auth_configured"] is True
        assert data["openai_configured"] is True

    def test_unhealthy_when_missing_openai(self, client, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        resp = client.get("/delegate/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["healthy"] is False
        assert data["openai_configured"] is False

    def test_unhealthy_when_missing_token(self, client, monkeypatch):
        monkeypatch.delenv(BACKUP_TOKEN_ENV)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        resp = client.get("/delegate/health")
        data = resp.json()
        assert data["healthy"] is False
        assert data["auth_configured"] is False
