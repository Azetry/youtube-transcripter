"""Tests for the alternate-host acquisition request/response contract (H4).

Validates serialisation round-trips, validation, factory helpers, and
the contract shape — without any transport or network concerns.
"""

import json
import pytest

from src.integrations.alternate_host import (
    AlternateHostRequest,
    AlternateHostResponse,
    FailureContext,
    RemoteAcquisitionStatus,
    RemoteVideoInfo,
    build_request_from_decision,
)
from src.models.acquisition import AcquisitionMode, FailureCategory


# ---------------------------------------------------------------------------
# FailureContext
# ---------------------------------------------------------------------------

class TestFailureContext:
    def test_defaults(self):
        ctx = FailureContext()
        assert ctx.last_category is None
        assert ctx.exhausted_modes == ()
        assert ctx.attempt_count == 0
        assert ctx.reason == ""

    def test_round_trip_dict(self):
        ctx = FailureContext(
            last_category=FailureCategory.AUTH_REQUIRED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE),
            attempt_count=2,
            reason="Auth failed after cookie attempt",
        )
        d = ctx.to_dict()
        restored = FailureContext.from_dict(d)
        assert restored == ctx

    def test_dict_shape(self):
        ctx = FailureContext(
            last_category=FailureCategory.GEO_BLOCKED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,),
            attempt_count=1,
            reason="blocked",
        )
        d = ctx.to_dict()
        assert d == {
            "last_category": "geo_blocked",
            "exhausted_modes": ["unauthenticated"],
            "attempt_count": 1,
            "reason": "blocked",
        }

    def test_from_dict_missing_fields(self):
        ctx = FailureContext.from_dict({})
        assert ctx.last_category is None
        assert ctx.exhausted_modes == ()
        assert ctx.attempt_count == 0

    def test_immutable(self):
        ctx = FailureContext()
        with pytest.raises(AttributeError):
            ctx.reason = "changed"


# ---------------------------------------------------------------------------
# AlternateHostRequest
# ---------------------------------------------------------------------------

class TestAlternateHostRequest:
    def test_minimal_request(self):
        req = AlternateHostRequest(url="https://youtube.com/watch?v=abc123")
        assert req.url == "https://youtube.com/watch?v=abc123"
        assert req.preferred_mode is None
        assert req.format == "mp3"
        assert req.quality == "64"
        assert req.download is True
        assert req.originator == ""
        assert req.failure_context is None

    def test_full_request(self):
        ctx = FailureContext(
            last_category=FailureCategory.AUTH_REQUIRED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,),
            attempt_count=1,
            reason="sign-in wall",
        )
        req = AlternateHostRequest(
            url="https://youtube.com/watch?v=abc123",
            preferred_mode=AcquisitionMode.COOKIE_FILE,
            format="m4a",
            quality="128",
            download=True,
            originator="dev-server-01",
            failure_context=ctx,
        )
        assert req.preferred_mode == AcquisitionMode.COOKIE_FILE
        assert req.format == "m4a"
        assert req.originator == "dev-server-01"
        assert req.failure_context is not None
        assert req.failure_context.last_category == FailureCategory.AUTH_REQUIRED

    def test_round_trip_dict(self):
        req = AlternateHostRequest(
            url="https://youtube.com/watch?v=xyz",
            preferred_mode=AcquisitionMode.COOKIE_BROWSER,
            originator="test",
            failure_context=FailureContext(
                last_category=FailureCategory.TRANSIENT,
                attempt_count=3,
            ),
        )
        d = req.to_dict()
        restored = AlternateHostRequest.from_dict(d)
        assert restored.url == req.url
        assert restored.preferred_mode == req.preferred_mode
        assert restored.originator == req.originator
        assert restored.failure_context.last_category == FailureCategory.TRANSIENT
        assert restored.failure_context.attempt_count == 3

    def test_round_trip_json(self):
        req = AlternateHostRequest(url="https://youtube.com/watch?v=j")
        raw = req.to_json()
        parsed = json.loads(raw)
        assert parsed["url"] == req.url
        restored = AlternateHostRequest.from_json(raw)
        assert restored == req

    def test_round_trip_no_failure_context(self):
        req = AlternateHostRequest(url="https://youtube.com/watch?v=noctx")
        d = req.to_dict()
        assert d["failure_context"] is None
        restored = AlternateHostRequest.from_dict(d)
        assert restored.failure_context is None

    def test_round_trip_no_preferred_mode(self):
        req = AlternateHostRequest(url="https://youtube.com/watch?v=nomode")
        d = req.to_dict()
        assert d["preferred_mode"] is None
        restored = AlternateHostRequest.from_dict(d)
        assert restored.preferred_mode is None

    def test_dict_is_json_serialisable(self):
        req = AlternateHostRequest(
            url="https://youtube.com/watch?v=ser",
            preferred_mode=AcquisitionMode.UNAUTHENTICATED,
            failure_context=FailureContext(
                last_category=FailureCategory.RATE_LIMITED,
                exhausted_modes=(AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE),
                attempt_count=2,
                reason="429 repeatedly",
            ),
        )
        raw = json.dumps(req.to_dict())
        assert isinstance(raw, str)
        parsed = json.loads(raw)
        assert parsed["url"] == req.url

    def test_immutable(self):
        req = AlternateHostRequest(url="https://youtube.com/watch?v=imm")
        with pytest.raises(AttributeError):
            req.url = "changed"

    def test_from_dict_defaults(self):
        req = AlternateHostRequest.from_dict({"url": "https://youtube.com/watch?v=d"})
        assert req.format == "mp3"
        assert req.quality == "64"
        assert req.download is True
        assert req.originator == ""


# ---------------------------------------------------------------------------
# RemoteVideoInfo
# ---------------------------------------------------------------------------

class TestRemoteVideoInfo:
    def test_defaults(self):
        vi = RemoteVideoInfo()
        assert vi.video_id == ""
        assert vi.title == ""
        assert vi.duration == 0
        assert vi.channel == ""
        assert vi.audio_url is None

    def test_round_trip_dict(self):
        vi = RemoteVideoInfo(
            video_id="abc123",
            title="Test Video",
            duration=300,
            channel="TestChannel",
            audio_url="https://remote-host/audio/abc123.mp3",
        )
        d = vi.to_dict()
        restored = RemoteVideoInfo.from_dict(d)
        assert restored == vi

    def test_audio_url_optional(self):
        vi = RemoteVideoInfo(video_id="x")
        d = vi.to_dict()
        assert d["audio_url"] is None
        restored = RemoteVideoInfo.from_dict(d)
        assert restored.audio_url is None


# ---------------------------------------------------------------------------
# AlternateHostResponse
# ---------------------------------------------------------------------------

class TestAlternateHostResponse:
    def test_success_response(self):
        vi = RemoteVideoInfo(video_id="abc", title="Test", duration=120)
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.SUCCESS,
            video_info=vi,
            remote_host="worker-01",
        )
        assert resp.success is True
        assert resp.video_info.video_id == "abc"
        assert resp.error_message is None

    def test_failed_response(self):
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.FAILED,
            error_message="sign in to confirm you're not a bot",
            failure_category=FailureCategory.AUTH_REQUIRED,
            remote_host="worker-01",
        )
        assert resp.success is False
        assert resp.failure_category == FailureCategory.AUTH_REQUIRED

    def test_rejected_response(self):
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.REJECTED,
            error_message="host overloaded, try later",
        )
        assert resp.success is False
        assert resp.status == RemoteAcquisitionStatus.REJECTED

    def test_round_trip_dict_success(self):
        vi = RemoteVideoInfo(video_id="rt", title="Round Trip", duration=60)
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.SUCCESS,
            video_info=vi,
            remote_host="w1",
        )
        d = resp.to_dict()
        restored = AlternateHostResponse.from_dict(d)
        assert restored.success is True
        assert restored.video_info.video_id == "rt"
        assert restored.remote_host == "w1"

    def test_round_trip_dict_failure(self):
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.FAILED,
            error_message="timeout",
            failure_category=FailureCategory.TRANSIENT,
        )
        d = resp.to_dict()
        restored = AlternateHostResponse.from_dict(d)
        assert restored.success is False
        assert restored.error_message == "timeout"
        assert restored.failure_category == FailureCategory.TRANSIENT

    def test_round_trip_json(self):
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.SUCCESS,
            video_info=RemoteVideoInfo(video_id="j"),
        )
        raw = resp.to_json()
        restored = AlternateHostResponse.from_json(raw)
        assert restored.success is True
        assert restored.video_info.video_id == "j"

    def test_dict_is_json_serialisable(self):
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.FAILED,
            failure_category=FailureCategory.GEO_BLOCKED,
            error_message="geo-restricted",
            remote_host="eu-worker",
        )
        raw = json.dumps(resp.to_dict())
        assert isinstance(raw, str)

    def test_immutable(self):
        resp = AlternateHostResponse(status=RemoteAcquisitionStatus.SUCCESS)
        with pytest.raises(AttributeError):
            resp.status = RemoteAcquisitionStatus.FAILED

    def test_no_video_info_on_failure(self):
        resp = AlternateHostResponse(
            status=RemoteAcquisitionStatus.FAILED,
            error_message="err",
        )
        d = resp.to_dict()
        assert d["video_info"] is None
        restored = AlternateHostResponse.from_dict(d)
        assert restored.video_info is None


# ---------------------------------------------------------------------------
# RemoteAcquisitionStatus enum
# ---------------------------------------------------------------------------

class TestRemoteAcquisitionStatus:
    def test_values(self):
        assert RemoteAcquisitionStatus.SUCCESS.value == "success"
        assert RemoteAcquisitionStatus.FAILED.value == "failed"
        assert RemoteAcquisitionStatus.REJECTED.value == "rejected"

    def test_string_enum(self):
        assert str(RemoteAcquisitionStatus.SUCCESS) == "RemoteAcquisitionStatus.SUCCESS"
        assert RemoteAcquisitionStatus("success") == RemoteAcquisitionStatus.SUCCESS


# ---------------------------------------------------------------------------
# build_request_from_decision factory
# ---------------------------------------------------------------------------

class TestBuildRequestFromDecision:
    def test_minimal(self):
        req = build_request_from_decision("https://youtube.com/watch?v=min")
        assert req.url == "https://youtube.com/watch?v=min"
        assert req.failure_context is None
        assert req.format == "mp3"
        assert req.quality == "64"
        assert req.download is True

    def test_with_failure_context(self):
        req = build_request_from_decision(
            "https://youtube.com/watch?v=fc",
            failure_category=FailureCategory.AUTH_REQUIRED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED, AcquisitionMode.COOKIE_FILE),
            attempt_count=2,
            reason="auth tried and failed",
            originator="test-host",
        )
        assert req.failure_context is not None
        assert req.failure_context.last_category == FailureCategory.AUTH_REQUIRED
        assert len(req.failure_context.exhausted_modes) == 2
        assert req.failure_context.attempt_count == 2
        assert req.originator == "test-host"

    def test_custom_format(self):
        req = build_request_from_decision(
            "https://youtube.com/watch?v=fmt",
            format="m4a",
            quality="128",
            download=False,
        )
        assert req.format == "m4a"
        assert req.quality == "128"
        assert req.download is False

    def test_no_context_when_no_failure_info(self):
        """No failure_context created when all failure fields are empty."""
        req = build_request_from_decision(
            "https://youtube.com/watch?v=empty",
            originator="host",
        )
        assert req.failure_context is None

    def test_context_created_with_reason_only(self):
        req = build_request_from_decision(
            "https://youtube.com/watch?v=reason",
            reason="operator manually delegated",
        )
        assert req.failure_context is not None
        assert req.failure_context.reason == "operator manually delegated"

    def test_round_trip_through_json(self):
        """Factory → to_json → from_json should preserve all fields."""
        req = build_request_from_decision(
            "https://youtube.com/watch?v=rtj",
            failure_category=FailureCategory.RATE_LIMITED,
            exhausted_modes=(AcquisitionMode.UNAUTHENTICATED,),
            attempt_count=1,
            reason="429",
            originator="ci",
            format="m4a",
            quality="192",
        )
        raw = req.to_json()
        restored = AlternateHostRequest.from_json(raw)
        assert restored.url == req.url
        assert restored.failure_context.last_category == FailureCategory.RATE_LIMITED
        assert restored.originator == "ci"
        assert restored.format == "m4a"
