"""Health-check support for the backup service.

Unit H7a: defines the health response shape and a builder for the
backup service's GET /health endpoint.

The health check confirms:
  1. The service is running and accepting requests.
  2. Whether required dependencies (OpenAI key, token) are configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from src.integrations.backup_auth import get_configured_token


@dataclass(frozen=True)
class BackupHealthStatus:
    """Health-check response payload for the backup service.

    Attributes:
        healthy: Overall health flag.
        service: Service identifier.
        auth_configured: Whether a backup-service bearer token is set.
        openai_configured: Whether an OpenAI API key is set.
        detail: Optional human-readable detail on unhealthy state.
    """
    healthy: bool
    service: str = "youtube-transcripter-backup"
    auth_configured: bool = False
    openai_configured: bool = False
    detail: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "healthy": self.healthy,
            "service": self.service,
            "auth_configured": self.auth_configured,
            "openai_configured": self.openai_configured,
        }
        if self.detail is not None:
            d["detail"] = self.detail
        return d


def check_backup_health() -> BackupHealthStatus:
    """Build a health status by inspecting the runtime environment."""
    token_ok = get_configured_token() is not None
    openai_ok = bool(os.environ.get("OPENAI_API_KEY", "").strip())

    healthy = token_ok and openai_ok

    detail = None
    if not healthy:
        missing = []
        if not token_ok:
            missing.append("BACKUP_SERVICE_TOKEN")
        if not openai_ok:
            missing.append("OPENAI_API_KEY")
        detail = f"missing env: {', '.join(missing)}"

    return BackupHealthStatus(
        healthy=healthy,
        auth_configured=token_ok,
        openai_configured=openai_ok,
        detail=detail,
    )
