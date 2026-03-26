"""Tests for YouTubeExtractor authentication / cookie option building."""

import os
from unittest.mock import patch

import pytest

from src.youtube_extractor import YouTubeExtractor


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
        assert call_opts["format"] == "bestaudio/best"  # existing opts preserved
