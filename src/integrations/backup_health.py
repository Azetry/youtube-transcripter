"""Runtime health snapshot for diagnostics (OpenAI, optional YouTube auth env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BackupHealthStatus:
    """Structured health payload for `/api/health` and operators."""

    healthy: bool
    service: str = "youtube-transcripter"
    openai_configured: bool = False
    yt_auth_configured: bool = False
    yt_auth_mode: Optional[str] = None
    service_role: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "healthy": self.healthy,
            "service": self.service,
            "openai_configured": self.openai_configured,
            "yt_auth_configured": self.yt_auth_configured,
        }
        if self.yt_auth_mode is not None:
            d["yt_auth_mode"] = self.yt_auth_mode
        if self.service_role is not None:
            d["service_role"] = self.service_role
        if self.detail is not None:
            d["detail"] = self.detail
        return d


def check_backup_health() -> BackupHealthStatus:
    """Inspect env for core transcription and optional yt-dlp cookie modes."""
    openai_ok = bool(os.environ.get("OPENAI_API_KEY", "").strip())

    cookies_file = os.environ.get("YT_DLP_COOKIES_FILE", "").strip()
    cookies_browser = os.environ.get("YT_DLP_COOKIES_FROM_BROWSER", "").strip()
    yt_auth_mode = None
    if cookies_file:
        yt_auth_mode = "cookie_file"
    elif cookies_browser:
        yt_auth_mode = "cookie_browser"
    yt_auth_ok = yt_auth_mode is not None

    healthy = openai_ok
    detail = None
    if not healthy:
        detail = "missing env: OPENAI_API_KEY"

    service_role = os.environ.get("SERVICE_ROLE") or None

    return BackupHealthStatus(
        healthy=healthy,
        openai_configured=openai_ok,
        yt_auth_configured=yt_auth_ok,
        yt_auth_mode=yt_auth_mode,
        service_role=service_role,
        detail=detail,
    )
