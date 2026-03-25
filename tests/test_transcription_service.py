"""Tests for TranscriptionService (URL validation only - pipeline requires external APIs)."""

from src.services.transcription_service import TranscriptionService


def test_validate_url_valid():
    svc = TranscriptionService()
    assert svc.validate_url("https://www.youtube.com/watch?v=abc123") is True
    assert svc.validate_url("https://youtu.be/abc123") is True
    assert svc.validate_url("https://youtube.com/shorts/abc123") is True


def test_validate_url_invalid():
    svc = TranscriptionService()
    assert svc.validate_url("https://example.com") is False
    assert svc.validate_url("not-a-url") is False
    assert svc.validate_url("") is False
