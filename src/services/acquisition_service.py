"""This-host acquisition service with structured strategy selection and diagnostics.

Unit H2: makes extraction attempts structured and diagnosable by running
strategies in a controlled order and recording classified outcomes.

The service wraps YouTubeExtractor and produces an AcquisitionResult that
downstream code (and later H3 fallback routing) can inspect without parsing
raw error strings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from src.models.acquisition import (
    AcquisitionAttempt,
    AcquisitionMode,
    FailureCategory,
    FallbackAction,
    suggest_fallback,
)
from src.youtube_extractor import YouTubeExtractor, VideoInfo

_AUDIO_FORMAT_SELECTORS: tuple[str, ...] = (
    "bestaudio[ext=m4a]/bestaudio/best",
    "bestaudio/best",
    "best",
)


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

def _has_cookie_file() -> bool:
    return bool(os.environ.get("YT_DLP_COOKIES_FILE"))


def _has_cookie_browser() -> bool:
    return bool(os.environ.get("YT_DLP_COOKIES_FROM_BROWSER"))


def auth_configured() -> bool:
    """Return True if any cookie-based auth env var is set."""
    return _has_cookie_file() or _has_cookie_browser()


def _detect_auth_mode() -> Optional[AcquisitionMode]:
    """Return the auth mode implied by current env, or None."""
    if _has_cookie_file():
        return AcquisitionMode.COOKIE_FILE
    if _has_cookie_browser():
        return AcquisitionMode.COOKIE_BROWSER
    return None


def build_strategy_order(*, auth_first: bool = False) -> list[AcquisitionMode]:
    """Return the ordered list of modes to attempt on this host.

    Default (auth_first=False):
        1. UNAUTHENTICATED
        2. auth mode (if configured)

    With auth_first=True (useful when unauthenticated is known to fail):
        1. auth mode (if configured)
        2. UNAUTHENTICATED  (still tried as last resort)

    If no auth is configured the list contains only UNAUTHENTICATED.
    """
    auth_mode = _detect_auth_mode()
    if auth_mode is None:
        return [AcquisitionMode.UNAUTHENTICATED]

    if auth_first:
        return [auth_mode, AcquisitionMode.UNAUTHENTICATED]
    return [AcquisitionMode.UNAUTHENTICATED, auth_mode]


# ---------------------------------------------------------------------------
# Acquisition result — structured diagnostic output
# ---------------------------------------------------------------------------

@dataclass
class AcquisitionResult:
    """Outcome of a this-host acquisition attempt sequence.

    Attributes:
        video_info: VideoInfo on success, None on failure.
        success: True if any strategy succeeded.
        attempts: Ordered list of AcquisitionAttempts tried.
        final_action: Suggested next action for the orchestrator.
    """
    video_info: Optional[VideoInfo] = None
    success: bool = False
    attempts: list[AcquisitionAttempt] = field(default_factory=list)
    final_action: Optional[FallbackAction] = None

    @property
    def strategy_count(self) -> int:
        return len(self.attempts)

    @property
    def last_failure_category(self) -> Optional[FailureCategory]:
        for attempt in reversed(self.attempts):
            if not attempt.success and attempt.failure_category is not None:
                return attempt.failure_category
        return None

    def diagnostics(self) -> dict:
        """Return a serialisable diagnostics summary."""
        return {
            "success": self.success,
            "strategies_tried": self.strategy_count,
            "attempts": [
                {
                    "mode": attempt.mode.value,
                    "success": attempt.success,
                    "error": attempt.error_message,
                    "failure_category": (
                        attempt.failure_category.value
                        if attempt.failure_category
                        else None
                    ),
                    "started_at": attempt.started_at,
                    "finished_at": attempt.finished_at,
                }
                for attempt in self.attempts
            ],
            "final_action": (
                self.final_action.value if self.final_action else None
            ),
        }


# ---------------------------------------------------------------------------
# Acquisition service
# ---------------------------------------------------------------------------

def _build_ydl_overrides(mode: AcquisitionMode) -> dict:
    """Return yt-dlp option overrides that force a specific mode.

    UNAUTHENTICATED: explicitly clear cookie options and use best-effort opts.
    COOKIE_FILE / COOKIE_BROWSER: delegate to YouTubeExtractor._build_auth_opts.
    """
    if mode == AcquisitionMode.UNAUTHENTICATED:
        return YouTubeExtractor._build_unauthenticated_opts()
    # For auth modes, let the extractor read env as normal
    return YouTubeExtractor._build_auth_opts()


class ThisHostAcquisitionService:
    """Runs this-host extraction strategies in order, recording structured results.

    Usage:
        svc = ThisHostAcquisitionService(extractor)
        result = svc.acquire(url)
        if not result.success:
            print(result.diagnostics())
    """

    def __init__(
        self,
        extractor: YouTubeExtractor,
        *,
        auth_first: bool = False,
    ) -> None:
        self._extractor = extractor
        self._auth_first = auth_first

    def acquire(
        self,
        url: str,
        *,
        download: bool = True,
        format: str = "mp3",
        quality: str = "64",
    ) -> AcquisitionResult:
        """Try each strategy in order; return on first success or after all fail.

        Args:
            url: YouTube URL.
            download: If True, download audio; otherwise extract info only.
            format: Audio format (only used when download=True).
            quality: Audio quality kbps (only used when download=True).
        """
        strategies = build_strategy_order(auth_first=self._auth_first)
        result = AcquisitionResult()

        for mode in strategies:
            attempt = AcquisitionAttempt(mode=mode)
            result.attempts.append(attempt)

            try:
                video_info = self._run_extraction(
                    url, mode, download=download, format=format, quality=quality,
                )
                attempt.record_success()
                result.video_info = video_info
                result.success = True
                return result
            except Exception as exc:
                attempt.record_failure(str(exc))
                # Continue to next strategy

        # All strategies exhausted — compute final action hint
        last_cat = result.last_failure_category
        if last_cat is not None:
            result.final_action = suggest_fallback(
                last_cat, auth_configured=auth_configured(),
            )
        else:
            result.final_action = FallbackAction.ABORT

        return result

    def _run_extraction(
        self,
        url: str,
        mode: AcquisitionMode,
        *,
        download: bool,
        format: str,
        quality: str,
    ) -> VideoInfo:
        """Execute a single extraction attempt using the given mode."""
        if download:
            return self._download_with_mode(url, mode, format=format, quality=quality)
        return self._extract_info_with_mode(url, mode)

    def _download_with_mode(
        self,
        url: str,
        mode: AcquisitionMode,
        *,
        format: str,
        quality: str,
    ) -> VideoInfo:
        """Download audio using yt-dlp options forced to a specific mode."""
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError

        base_opts = _build_ydl_overrides(mode)
        last_exc: Optional[DownloadError] = None
        info: Optional[dict] = None
        audio_file: Optional[str] = None

        for selector in _AUDIO_FORMAT_SELECTORS:
            opts = dict(base_opts)
            opts.update({
                "format": selector,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": format,
                    "preferredquality": quality,
                }],
                "outtmpl": f"{self._extractor.output_dir}/%(id)s.%(ext)s",
                "quiet": False,
                "no_warnings": False,
            })
            try:
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    audio_file = f"{self._extractor.output_dir}/{info.get('id')}.{format}"
                    break
            except DownloadError as exc:
                last_exc = exc
                if "Requested format is not available" not in str(exc):
                    raise

        if info is None or audio_file is None:
            if last_exc is not None:
                raise last_exc
            raise DownloadError("Audio acquisition failed: no format selector succeeded.")

        return VideoInfo(
            video_id=info.get("id", ""),
            title=info.get("title", ""),
            description=info.get("description", ""),
            duration=info.get("duration", 0),
            upload_date=info.get("upload_date", ""),
            channel=info.get("uploader", ""),
            channel_id=info.get("channel_id", ""),
            view_count=info.get("view_count", 0),
            thumbnail_url=info.get("thumbnail", ""),
            audio_file=audio_file,
        )

    def _extract_info_with_mode(self, url: str, mode: AcquisitionMode) -> VideoInfo:
        """Extract metadata only, using options forced to a specific mode."""
        from yt_dlp import YoutubeDL

        opts = _build_ydl_overrides(mode)
        opts.update({"quiet": True, "no_warnings": True})

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return VideoInfo(
            video_id=info.get("id", ""),
            title=info.get("title", ""),
            description=info.get("description", ""),
            duration=info.get("duration", 0),
            upload_date=info.get("upload_date", ""),
            channel=info.get("uploader", ""),
            channel_id=info.get("channel_id", ""),
            view_count=info.get("view_count", 0),
            thumbnail_url=info.get("thumbnail", ""),
        )
