"""Tests for the backup-service delegation contract (H7a).

Validates serialisation round-trips, field defaults, immutability,
and the contract shape for DelegationRequest, DelegationResult,
and DelegationResponse.
"""

import json
import pytest

from src.integrations.backup_service import (
    DelegationRequest,
    DelegationResponse,
    DelegationResult,
    DelegationStatus,
)
from src.models.acquisition import FailureCategory


# ---------------------------------------------------------------------------
# DelegationStatus
# ---------------------------------------------------------------------------

class TestDelegationStatus:
    def test_values(self):
        assert DelegationStatus.SUCCESS.value == "success"
        assert DelegationStatus.FAILED.value == "failed"
        assert DelegationStatus.REJECTED.value == "rejected"

    def test_from_string(self):
        assert DelegationStatus("success") == DelegationStatus.SUCCESS
        assert DelegationStatus("rejected") == DelegationStatus.REJECTED


# ---------------------------------------------------------------------------
# DelegationRequest
# ---------------------------------------------------------------------------

class TestDelegationRequest:
    def test_minimal(self):
        req = DelegationRequest(url="https://youtube.com/watch?v=abc")
        assert req.url == "https://youtube.com/watch?v=abc"
        assert req.language is None
        assert req.skip_correction is False
        assert req.custom_terms == ()
        assert req.originator == ""
        assert req.delegation_reason == ""
        assert req.acquisition_failure_context is None
        assert req.job_id is None

    def test_full_request(self):
        req = DelegationRequest(
            url="https://youtube.com/watch?v=xyz",
            language="zh",
            skip_correction=True,
            custom_terms=("API", "SDK"),
            originator="primary-01",
            delegation_reason="auth_required after 2 attempts",
            acquisition_failure_context="cookie expired, sign-in wall hit",
            job_id="job-12345",
        )
        assert req.language == "zh"
        assert req.skip_correction is True
        assert req.custom_terms == ("API", "SDK")
        assert req.originator == "primary-01"
        assert req.job_id == "job-12345"

    def test_round_trip_dict(self):
        req = DelegationRequest(
            url="https://youtube.com/watch?v=rt",
            language="en",
            custom_terms=("React",),
            originator="host-a",
            delegation_reason="rate limited",
            job_id="j1",
        )
        d = req.to_dict()
        restored = DelegationRequest.from_dict(d)
        assert restored.url == req.url
        assert restored.language == req.language
        assert restored.custom_terms == req.custom_terms
        assert restored.originator == req.originator
        assert restored.delegation_reason == req.delegation_reason
        assert restored.job_id == req.job_id

    def test_round_trip_json(self):
        req = DelegationRequest(
            url="https://youtube.com/watch?v=json",
            custom_terms=("A", "B"),
        )
        raw = req.to_json()
        restored = DelegationRequest.from_json(raw)
        assert restored == req

    def test_custom_terms_serialised_as_list(self):
        req = DelegationRequest(
            url="https://youtube.com/watch?v=ct",
            custom_terms=("X", "Y"),
        )
        d = req.to_dict()
        assert isinstance(d["custom_terms"], list)
        assert d["custom_terms"] == ["X", "Y"]

    def test_from_dict_defaults(self):
        req = DelegationRequest.from_dict({"url": "https://youtube.com/watch?v=d"})
        assert req.language is None
        assert req.skip_correction is False
        assert req.custom_terms == ()
        assert req.originator == ""

    def test_dict_is_json_serialisable(self):
        req = DelegationRequest(
            url="https://youtube.com/watch?v=ser",
            language="ja",
            custom_terms=("term",),
            acquisition_failure_context="some context",
        )
        raw = json.dumps(req.to_dict())
        assert isinstance(raw, str)
        parsed = json.loads(raw)
        assert parsed["url"] == req.url

    def test_immutable(self):
        req = DelegationRequest(url="https://youtube.com/watch?v=imm")
        with pytest.raises(AttributeError):
            req.url = "changed"


# ---------------------------------------------------------------------------
# DelegationResult
# ---------------------------------------------------------------------------

class TestDelegationResult:
    def test_defaults(self):
        r = DelegationResult()
        assert r.video_id == ""
        assert r.title == ""
        assert r.channel == ""
        assert r.duration == 0
        assert r.original_text == ""
        assert r.corrected_text == ""
        assert r.language == ""

    def test_round_trip_dict(self):
        r = DelegationResult(
            video_id="v1",
            title="Test Video",
            channel="TestChan",
            duration=300,
            original_text="hello world",
            corrected_text="Hello, world.",
            language="en",
        )
        d = r.to_dict()
        restored = DelegationResult.from_dict(d)
        assert restored == r

    def test_from_dict_missing_fields(self):
        r = DelegationResult.from_dict({})
        assert r.video_id == ""
        assert r.duration == 0

    def test_immutable(self):
        r = DelegationResult()
        with pytest.raises(AttributeError):
            r.video_id = "changed"


# ---------------------------------------------------------------------------
# DelegationResponse
# ---------------------------------------------------------------------------

class TestDelegationResponse:
    def test_success_response(self):
        result = DelegationResult(video_id="abc", title="Test", duration=120)
        resp = DelegationResponse(
            status=DelegationStatus.SUCCESS,
            remote_host="backup-01",
            result=result,
        )
        assert resp.success is True
        assert resp.delegated is True
        assert resp.result.video_id == "abc"
        assert resp.error_message is None

    def test_failed_response(self):
        resp = DelegationResponse(
            status=DelegationStatus.FAILED,
            error_message="acquisition failed on backup host",
            failure_category=FailureCategory.AUTH_REQUIRED,
            remote_host="backup-01",
        )
        assert resp.success is False
        assert resp.failure_category == FailureCategory.AUTH_REQUIRED

    def test_rejected_response(self):
        resp = DelegationResponse(
            status=DelegationStatus.REJECTED,
            error_message="service overloaded",
        )
        assert resp.success is False
        assert resp.status == DelegationStatus.REJECTED

    def test_round_trip_dict_success(self):
        result = DelegationResult(
            video_id="rt",
            title="Round Trip",
            duration=60,
            original_text="text",
            corrected_text="Text.",
            language="en",
        )
        resp = DelegationResponse(
            status=DelegationStatus.SUCCESS,
            remote_host="w1",
            result=result,
            acquisition_diagnostics="all ok",
        )
        d = resp.to_dict()
        restored = DelegationResponse.from_dict(d)
        assert restored.success is True
        assert restored.result.video_id == "rt"
        assert restored.result.original_text == "text"
        assert restored.remote_host == "w1"
        assert restored.acquisition_diagnostics == "all ok"

    def test_round_trip_dict_failure(self):
        resp = DelegationResponse(
            status=DelegationStatus.FAILED,
            error_message="timeout",
            failure_category=FailureCategory.TRANSIENT,
        )
        d = resp.to_dict()
        restored = DelegationResponse.from_dict(d)
        assert restored.success is False
        assert restored.error_message == "timeout"
        assert restored.failure_category == FailureCategory.TRANSIENT

    def test_round_trip_json(self):
        resp = DelegationResponse(
            status=DelegationStatus.SUCCESS,
            result=DelegationResult(video_id="j"),
        )
        raw = resp.to_json()
        restored = DelegationResponse.from_json(raw)
        assert restored.success is True
        assert restored.result.video_id == "j"

    def test_dict_is_json_serialisable(self):
        resp = DelegationResponse(
            status=DelegationStatus.FAILED,
            failure_category=FailureCategory.GEO_BLOCKED,
            error_message="geo-restricted",
            remote_host="eu-backup",
        )
        raw = json.dumps(resp.to_dict())
        assert isinstance(raw, str)

    def test_immutable(self):
        resp = DelegationResponse(status=DelegationStatus.SUCCESS)
        with pytest.raises(AttributeError):
            resp.status = DelegationStatus.FAILED

    def test_no_result_on_failure(self):
        resp = DelegationResponse(
            status=DelegationStatus.FAILED,
            error_message="err",
        )
        d = resp.to_dict()
        assert d["result"] is None
        restored = DelegationResponse.from_dict(d)
        assert restored.result is None

    def test_delegated_always_true_by_default(self):
        resp = DelegationResponse(status=DelegationStatus.SUCCESS)
        assert resp.delegated is True
        d = resp.to_dict()
        assert d["delegated"] is True

    def test_diagnostics_optional(self):
        resp = DelegationResponse(
            status=DelegationStatus.SUCCESS,
            result=DelegationResult(video_id="diag"),
            acquisition_diagnostics="2 attempts, cookie fallback used",
        )
        d = resp.to_dict()
        assert d["acquisition_diagnostics"] == "2 attempts, cookie fallback used"
        restored = DelegationResponse.from_dict(d)
        assert restored.acquisition_diagnostics == "2 attempts, cookie fallback used"
