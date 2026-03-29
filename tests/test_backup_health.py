"""Tests for runtime health snapshot (OpenAI + optional yt-dlp cookie env)."""

import pytest

from src.integrations.backup_health import (
    BackupHealthStatus,
    check_backup_health,
)


class TestBackupHealthStatus:
    def test_healthy_to_dict(self):
        h = BackupHealthStatus(
            healthy=True,
            openai_configured=True,
            yt_auth_configured=False,
        )
        d = h.to_dict()
        assert d["healthy"] is True
        assert d["service"] == "youtube-transcripter"
        assert d["openai_configured"] is True
        assert d["yt_auth_configured"] is False
        assert "detail" not in d

    def test_unhealthy_includes_detail(self):
        h = BackupHealthStatus(
            healthy=False,
            detail="missing env: OPENAI_API_KEY",
        )
        d = h.to_dict()
        assert d["healthy"] is False
        assert d["detail"] == "missing env: OPENAI_API_KEY"

    def test_immutable(self):
        h = BackupHealthStatus(healthy=True)
        with pytest.raises(AttributeError):
            h.healthy = False


class TestCheckBackupHealth:
    def test_healthy_when_openai_configured(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.delenv("YT_DLP_COOKIES_FILE", raising=False)
        monkeypatch.delenv("YT_DLP_COOKIES_FROM_BROWSER", raising=False)
        status = check_backup_health()
        assert status.healthy is True
        assert status.openai_configured is True
        assert status.yt_auth_configured is False
        assert status.detail is None

    def test_unhealthy_missing_openai(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        status = check_backup_health()
        assert status.healthy is False
        assert status.openai_configured is False
        assert "OPENAI_API_KEY" in (status.detail or "")

    def test_yt_auth_reflects_cookie_file(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk")
        monkeypatch.setenv("YT_DLP_COOKIES_FILE", "/tmp/c.txt")
        status = check_backup_health()
        assert status.yt_auth_configured is True
        assert status.yt_auth_mode == "cookie_file"
        d = status.to_dict()
        assert d["yt_auth_mode"] == "cookie_file"

    def test_empty_openai_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "  ")
        status = check_backup_health()
        assert status.healthy is False

    def test_service_name_default(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        status = check_backup_health()
        assert status.service == "youtube-transcripter"
