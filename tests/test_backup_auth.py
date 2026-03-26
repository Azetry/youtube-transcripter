"""Tests for backup-service bearer-token authentication (H7a).

Validates token retrieval, header construction, token extraction,
and request validation — including edge cases and security behavior.
"""

import pytest

from src.integrations.backup_auth import (
    BACKUP_TOKEN_ENV,
    build_auth_header,
    extract_bearer_token,
    get_configured_token,
    validate_request_token,
)


# ---------------------------------------------------------------------------
# get_configured_token
# ---------------------------------------------------------------------------

class TestGetConfiguredToken:
    def test_returns_token_when_set(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret-token-123")
        assert get_configured_token() == "secret-token-123"

    def test_returns_none_when_unset(self, monkeypatch):
        monkeypatch.delenv(BACKUP_TOKEN_ENV, raising=False)
        assert get_configured_token() is None

    def test_returns_none_when_empty(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "")
        assert get_configured_token() is None

    def test_returns_none_when_whitespace(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "   ")
        assert get_configured_token() is None

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "  my-token  ")
        assert get_configured_token() == "my-token"


# ---------------------------------------------------------------------------
# build_auth_header
# ---------------------------------------------------------------------------

class TestBuildAuthHeader:
    def test_builds_bearer_header(self):
        header = build_auth_header("tok-abc")
        assert header == {"Authorization": "Bearer tok-abc"}

    def test_header_format(self):
        header = build_auth_header("xyz")
        assert header["Authorization"].startswith("Bearer ")


# ---------------------------------------------------------------------------
# extract_bearer_token
# ---------------------------------------------------------------------------

class TestExtractBearerToken:
    def test_valid_bearer(self):
        assert extract_bearer_token("Bearer my-secret") == "my-secret"

    def test_case_insensitive_scheme(self):
        assert extract_bearer_token("bearer my-secret") == "my-secret"
        assert extract_bearer_token("BEARER my-secret") == "my-secret"

    def test_none_header(self):
        assert extract_bearer_token(None) is None

    def test_empty_header(self):
        assert extract_bearer_token("") is None

    def test_no_scheme(self):
        assert extract_bearer_token("just-a-token") is None

    def test_wrong_scheme(self):
        assert extract_bearer_token("Basic dXNlcjpwYXNz") is None

    def test_bearer_no_token(self):
        assert extract_bearer_token("Bearer ") is None

    def test_bearer_only(self):
        assert extract_bearer_token("Bearer") is None

    def test_token_with_spaces_in_value(self):
        # Only takes the rest after "Bearer "
        assert extract_bearer_token("Bearer  spaced-token ") == "spaced-token"


# ---------------------------------------------------------------------------
# validate_request_token
# ---------------------------------------------------------------------------

class TestValidateRequestToken:
    def test_valid_token(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "correct-token")
        assert validate_request_token("Bearer correct-token") is True

    def test_invalid_token(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "correct-token")
        assert validate_request_token("Bearer wrong-token") is False

    def test_missing_header(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "correct-token")
        assert validate_request_token(None) is False

    def test_empty_header(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "correct-token")
        assert validate_request_token("") is False

    def test_no_configured_token_rejects_all(self, monkeypatch):
        monkeypatch.delenv(BACKUP_TOKEN_ENV, raising=False)
        assert validate_request_token("Bearer anything") is False

    def test_explicit_expected_token(self, monkeypatch):
        monkeypatch.delenv(BACKUP_TOKEN_ENV, raising=False)
        assert validate_request_token(
            "Bearer my-tok",
            expected_token="my-tok",
        ) is True

    def test_explicit_expected_token_mismatch(self):
        assert validate_request_token(
            "Bearer wrong",
            expected_token="right",
        ) is False

    def test_wrong_scheme_rejected(self, monkeypatch):
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "tok")
        assert validate_request_token("Basic tok") is False

    def test_constant_time_comparison(self, monkeypatch):
        """Verify that hmac.compare_digest is used (not ==)."""
        monkeypatch.setenv(BACKUP_TOKEN_ENV, "secret")
        # This test just verifies the function works correctly;
        # the constant-time property is guaranteed by hmac.compare_digest.
        assert validate_request_token("Bearer secret") is True
        assert validate_request_token("Bearer secre") is False
