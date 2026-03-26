"""Tests for backup-service health check (H7a).

Validates the health-check builder under various environment
configurations.
"""

import pytest

from src.integrations.backup_auth import BACKUP_TOKEN_ENV
from src.integrations.backup_health import (
    BackupHealthStatus,
    check_backup_health,
)


# ---------------------------------------------------------------------------
# BackupHealthStatus
# ---------------------------------------------------------------------------

class TestBackupHealthStatus:
    def test_healthy_to_dict(self):
        h = BackupHealthStatus(
            healthy=True,
            auth_configured=True,
            openai_configured=True,
        )
        d = h.to_dict()
        assert d["healthy"] is True
        assert d["service"] == "youtube-transcripter-backup"
        assert d["auth_configured"] is True
        assert d["openai_configured"] is True
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


# ---------------------------------------------------------------------------
# check_backup_health
# ---------------------------------------------------------------------------

class TestCheckBackupHealth:
    def test_healthy_when_both_configured(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "tok")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        status = check_backup_health()
        assert status.healthy is True
        assert status.auth_configured is True
        assert status.openai_configured is True
        assert status.detail is None

    def test_unhealthy_missing_token(self, monkeypatch):
        monkeypatch.delenv(BACKUP_TOKEN_ENV, raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        status = check_backup_health()
        assert status.healthy is False
        assert status.auth_configured is False
        assert status.openai_configured is True
        assert "BACKUP_SERVICE_TOKEN" in status.detail

    def test_unhealthy_missing_openai(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "tok")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        status = check_backup_health()
        assert status.healthy is False
        assert status.auth_configured is True
        assert status.openai_configured is False
        assert "OPENAI_API_KEY" in status.detail

    def test_unhealthy_missing_both(self, monkeypatch):
        monkeypatch.delenv(BACKUP_TOKEN_ENV, raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        status = check_backup_health()
        assert status.healthy is False
        assert status.auth_configured is False
        assert status.openai_configured is False
        assert "BACKUP_SERVICE_TOKEN" in status.detail
        assert "OPENAI_API_KEY" in status.detail

    def test_empty_values_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "  ")
        monkeypatch.setenv("OPENAI_API_KEY", "")
        status = check_backup_health()
        assert status.healthy is False

    def test_service_name(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "t")
        monkeypatch.setenv("OPENAI_API_KEY", "k")
        status = check_backup_health()
        assert status.service == "youtube-transcripter-backup"
