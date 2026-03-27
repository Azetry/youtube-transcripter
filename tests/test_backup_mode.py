"""Validate SERVICE_ROLE integration in backup health and API health."""

import os
import pytest
from src.integrations.backup_health import BackupHealthStatus, check_backup_health


class TestServiceRoleInBackupHealth:
    def test_service_role_omitted_when_none(self):
        h = BackupHealthStatus(healthy=True, auth_configured=True, openai_configured=True)
        d = h.to_dict()
        assert "service_role" not in d

    def test_service_role_present_when_set(self):
        h = BackupHealthStatus(healthy=True, service_role="backup")
        d = h.to_dict()
        assert d["service_role"] == "backup"

    def test_check_backup_health_picks_up_env(self, monkeypatch):
        monkeypatch.setenv("SERVICE_ROLE", "backup")
        monkeypatch.setenv("BACKUP_SERVICE_TOKEN", "tok")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        status = check_backup_health()
        assert status.service_role == "backup"
        assert status.to_dict()["service_role"] == "backup"

    def test_check_backup_health_no_service_role(self, monkeypatch):
        monkeypatch.delenv("SERVICE_ROLE", raising=False)
        monkeypatch.setenv("BACKUP_SERVICE_TOKEN", "tok")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        status = check_backup_health()
        assert status.service_role is None
        assert "service_role" not in status.to_dict()
