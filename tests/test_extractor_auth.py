"""Tests for YouTubeExtractor authentication / cookie option building."""

import os
from unittest.mock import patch

import pytest
from yt_dlp.utils import DownloadError

from src.youtube_extractor import (
    AuthBlockError,
    YouTubeExtractor,
    _AUTH_GUIDANCE,
    _is_auth_block_error,
)


# ---------------------------------------------------------------------------
# _build_auth_opts (existing Unit F tests, preserved)
# ---------------------------------------------------------------------------


class TestBuildAuthOpts:
    """Unit tests for _build_auth_opts env-driven option construction."""

    def test_no_env_vars_returns_empty(self):
        """Default: no auth options when env vars are absent."""
        with patch.dict(os.environ, {}, clear=True):
            assert YouTubeExtractor._build_auth_opts() == {}

    def test_cookies_file(self):
        env = {"YT_DLP_COOKIES_FILE": "/tmp/cookies.txt"}
        with patch.dict(os.environ, env, clear=True):
            opts = YouTubeExtractor._build_auth_opts()
            assert opts == {"cookiefile": "/tmp/cookies.txt"}

    def test_cookies_from_browser_simple(self):
        env = {"YT_DLP_COOKIES_FROM_BROWSER": "firefox"}
        with patch.dict(os.environ, env, clear=True):
            opts = YouTubeExtractor._build_auth_opts()
            assert opts == {"cookiesfrombrowser": ("firefox",)}

    def test_cookies_from_browser_with_profile(self):
        env = {
            "YT_DLP_COOKIES_FROM_BROWSER": "chrome",
            "YT_DLP_BROWSER_PROFILE": "Default",
        }
        with patch.dict(os.environ, env, clear=True):
            opts = YouTubeExtractor._build_auth_opts()
            assert opts == {"cookiesfrombrowser": ("chrome:Default",)}

    def test_cookies_from_browser_with_profile_and_container(self):
        env = {
            "YT_DLP_COOKIES_FROM_BROWSER": "firefox",
            "YT_DLP_BROWSER_PROFILE": "myprofile",
            "YT_DLP_BROWSER_CONTAINER": "personal",
        }
        with patch.dict(os.environ, env, clear=True):
            opts = YouTubeExtractor._build_auth_opts()
            assert opts == {"cookiesfrombrowser": ("firefox:myprofile:personal",)}

    def test_cookies_from_browser_with_container_no_profile(self):
        env = {
            "YT_DLP_COOKIES_FROM_BROWSER": "chrome",
            "YT_DLP_BROWSER_CONTAINER": "work",
        }
        with patch.dict(os.environ, env, clear=True):
            opts = YouTubeExtractor._build_auth_opts()
            assert opts == {"cookiesfrombrowser": ("chrome::work",)}

    def test_cookies_file_takes_precedence_over_browser(self):
        """When both are set, cookiefile wins (yt-dlp only accepts one)."""
        env = {
            "YT_DLP_COOKIES_FILE": "/tmp/cookies.txt",
            "YT_DLP_COOKIES_FROM_BROWSER": "chrome",
        }
        with patch.dict(os.environ, env, clear=True):
            opts = YouTubeExtractor._build_auth_opts()
            assert opts == {"cookiefile": "/tmp/cookies.txt"}
            assert "cookiesfrombrowser" not in opts

    def test_profile_and_container_ignored_without_browser(self):
        """Profile/container env vars alone do nothing."""
        env = {
            "YT_DLP_BROWSER_PROFILE": "Default",
            "YT_DLP_BROWSER_CONTAINER": "personal",
        }
        with patch.dict(os.environ, env, clear=True):
            assert YouTubeExtractor._build_auth_opts() == {}


# ---------------------------------------------------------------------------
# _build_unauthenticated_opts
# ---------------------------------------------------------------------------


class TestBuildUnauthenticatedOpts:
    def test_returns_extractor_args(self):
        opts = YouTubeExtractor._build_unauthenticated_opts()
        assert "extractor_args" in opts
        assert "youtube" in opts["extractor_args"]

    def test_includes_socket_timeout(self):
        opts = YouTubeExtractor._build_unauthenticated_opts()
        assert opts["socket_timeout"] == 30


# ---------------------------------------------------------------------------
# _build_ydl_opts (merged option builder)
# ---------------------------------------------------------------------------


class TestBuildYdlOpts:
    def test_no_auth_uses_unauthenticated_profile(self):
        with patch.dict(os.environ, {}, clear=True):
            opts = YouTubeExtractor._build_ydl_opts(quiet=True)
            assert "extractor_args" in opts
            assert opts["quiet"] is True
            assert "cookiefile" not in opts

    def test_auth_configured_skips_unauthenticated_profile(self):
        env = {"YT_DLP_COOKIES_FILE": "/tmp/c.txt"}
        with patch.dict(os.environ, env, clear=True):
            opts = YouTubeExtractor._build_ydl_opts(quiet=True)
            assert opts["cookiefile"] == "/tmp/c.txt"
            assert "extractor_args" not in opts

    def test_extra_kwargs_merged(self):
        with patch.dict(os.environ, {}, clear=True):
            opts = YouTubeExtractor._build_ydl_opts(format="bestaudio/best")
            assert opts["format"] == "bestaudio/best"


# ---------------------------------------------------------------------------
# Auth-block error detection
# ---------------------------------------------------------------------------


class TestAuthBlockDetection:
    @pytest.mark.parametrize("msg", [
        "Sign in to confirm your age",
        "ERROR: Please sign in",
        "This video requires login required to view",
        "Use --cookies or --cookies-from-browser",
        "bot detection: please verify",
        "confirm your age to watch",
        "age-restricted video",
        "captcha required",
        "consent page detected",
        "use cookies from browser to authenticate",
    ])
    def test_detects_auth_block_messages(self, msg):
        assert _is_auth_block_error(msg) is True

    @pytest.mark.parametrize("msg", [
        "Video unavailable",
        "HTTP Error 404: Not Found",
        "This video has been removed",
        "Network error: connection reset",
        "format not available",
    ])
    def test_non_auth_errors_not_flagged(self, msg):
        assert _is_auth_block_error(msg) is False


# ---------------------------------------------------------------------------
# AuthBlockError exception
# ---------------------------------------------------------------------------


class TestAuthBlockError:
    def test_contains_guidance(self):
        err = AuthBlockError("Sign in to confirm your age")
        assert "YT_DLP_COOKIES_FILE" in str(err)
        assert "YT_DLP_COOKIES_FROM_BROWSER" in str(err)
        assert "Sign in to confirm your age" in str(err)

    def test_preserves_original_error(self):
        err = AuthBlockError("bot detection")
        assert err.original_error == "bot detection"


# ---------------------------------------------------------------------------
# Integration: extract_info / download_audio error wrapping
# ---------------------------------------------------------------------------


class TestExtractorErrorWrapping:
    """Verify that DownloadError is re-raised as AuthBlockError when appropriate."""

    @patch("src.youtube_extractor.YoutubeDL")
    def test_extract_info_raises_auth_block(self, mock_ydl_cls):
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        mock_ydl.extract_info.side_effect = DownloadError("Sign in to confirm your age")

        ext = YouTubeExtractor("/tmp/test_dl")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AuthBlockError) as exc_info:
                ext.extract_info("https://youtube.com/watch?v=abc")
            assert "YT_DLP_COOKIES_FILE" in str(exc_info.value)

    @patch("src.youtube_extractor.YoutubeDL")
    def test_download_audio_raises_auth_block(self, mock_ydl_cls):
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        mock_ydl.extract_info.side_effect = DownloadError("bot detection required")

        ext = YouTubeExtractor("/tmp/test_dl")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(AuthBlockError):
                ext.download_audio("https://youtube.com/watch?v=abc")

    @patch("src.youtube_extractor.YoutubeDL")
    def test_non_auth_error_reraises_as_download_error(self, mock_ydl_cls):
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        mock_ydl.extract_info.side_effect = DownloadError("Video unavailable")

        ext = YouTubeExtractor("/tmp/test_dl")
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(DownloadError):
                ext.extract_info("https://youtube.com/watch?v=abc")

    @patch("src.youtube_extractor.YoutubeDL")
    def test_auth_configured_does_not_wrap_auth_error(self, mock_ydl_cls):
        """If cookies are configured but still fail, don't wrap — the user
        already tried auth, so the original error is more useful."""
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        mock_ydl.extract_info.side_effect = DownloadError("Sign in required")

        ext = YouTubeExtractor("/tmp/test_dl")
        env = {"YT_DLP_COOKIES_FILE": "/tmp/c.txt"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(DownloadError):
                ext.extract_info("https://youtube.com/watch?v=abc")


# ---------------------------------------------------------------------------
# Auth opts integration (existing tests, preserved)
# ---------------------------------------------------------------------------


class TestAuthOptsIntegration:
    """Verify auth opts are merged into ydl_opts used by extract/download."""

    @patch.object(YouTubeExtractor, "_build_auth_opts", return_value={"cookiefile": "/x.txt"})
    @patch("src.youtube_extractor.YoutubeDL")
    def test_extract_info_includes_auth(self, mock_ydl_cls, mock_auth):
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        mock_ydl.extract_info.return_value = {
            "id": "abc", "title": "t", "description": "", "duration": 60,
            "upload_date": "20240101", "uploader": "u", "channel_id": "c",
            "view_count": 1, "thumbnail": "",
        }
        ext = YouTubeExtractor("/tmp/test_dl")
        ext.extract_info("https://youtube.com/watch?v=abc")

        # The YoutubeDL constructor should have received cookiefile
        call_opts = mock_ydl_cls.call_args[0][0]
        assert call_opts["cookiefile"] == "/x.txt"

    @patch.object(YouTubeExtractor, "_build_auth_opts", return_value={"cookiefile": "/x.txt"})
    @patch("src.youtube_extractor.YoutubeDL")
    def test_download_audio_includes_auth(self, mock_ydl_cls, mock_auth):
        mock_ydl = mock_ydl_cls.return_value.__enter__.return_value
        mock_ydl.extract_info.return_value = {
            "id": "abc", "title": "t", "description": "", "duration": 60,
            "upload_date": "20240101", "uploader": "u", "channel_id": "c",
            "view_count": 1, "thumbnail": "",
        }
        ext = YouTubeExtractor("/tmp/test_dl")
        ext.download_audio("https://youtube.com/watch?v=abc")

        call_opts = mock_ydl_cls.call_args[0][0]
        assert call_opts["cookiefile"] == "/x.txt"
        assert call_opts["format"] == "bestaudio[ext=m4a]/bestaudio/best"  # existing opts preserved
