"""A-side HTTP client for delegating transcription to a backup service.

Unit H7c: sends a DelegationRequest to the backup service's
``/delegate/transcribe`` endpoint and returns the parsed
DelegationResponse.

Design:
  - Uses stdlib ``urllib.request`` — no extra dependencies.
  - Internal-network only; no retries or advanced backoff.
  - Reuses H7a auth (bearer token) and contract models.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import urllib.error
import urllib.request
from typing import Optional

from src.integrations.backup_auth import build_auth_header, get_configured_token
from src.integrations.backup_service import (
    DelegationRequest,
    DelegationResponse,
    DelegationStatus,
)
from src.models.acquisition import FailureCategory

logger = logging.getLogger(__name__)

# Environment variable for the backup service base URL.
BACKUP_SERVICE_URL_ENV = "BACKUP_SERVICE_URL"

# Default timeout for the HTTP call (seconds).  Transcription can take
# a while on the remote side, so we use a generous timeout.
_DEFAULT_TIMEOUT = 300


class BackupClientError(Exception):
    """Raised when the backup client cannot complete the delegation call.

    This wraps transport-level failures (connection refused, timeout, bad
    status codes) so callers can distinguish them from pipeline errors.
    """


def get_backup_service_url() -> Optional[str]:
    """Return the configured backup service URL, or None if unset."""
    url = os.environ.get(BACKUP_SERVICE_URL_ENV, "").strip().rstrip("/")
    return url if url else None


def delegate_transcription(
    request: DelegationRequest,
    *,
    base_url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: int = _DEFAULT_TIMEOUT,
) -> DelegationResponse:
    """Send a delegation request to the backup service.

    Args:
        request: The DelegationRequest to send.
        base_url: Override for the backup service URL (default: from env).
        token: Override for the bearer token (default: from env).
        timeout: HTTP timeout in seconds.

    Returns:
        Parsed DelegationResponse from the backup service.

    Raises:
        BackupClientError: If the call cannot be completed (network error,
            bad status, missing config, malformed response).
    """
    url = base_url or get_backup_service_url()
    if not url:
        raise BackupClientError(
            f"Backup service URL not configured (set {BACKUP_SERVICE_URL_ENV})"
        )

    token = token or get_configured_token()
    if not token:
        raise BackupClientError(
            "Backup service token not configured (set BACKUP_SERVICE_TOKEN)"
        )

    endpoint = f"{url}/delegate/transcribe"
    body = json.dumps(request.to_dict()).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        **build_auth_header(token),
    }

    http_request = urllib.request.Request(
        endpoint,
        data=body,
        headers=headers,
        method="POST",
    )

    logger.info(
        "Delegating transcription to %s (job_id=%s)",
        endpoint,
        request.job_id,
    )

    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as resp:
            resp_body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise BackupClientError(
            f"Backup service returned HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        raise BackupClientError(
            f"Cannot reach backup service at {endpoint}: {exc}"
        ) from exc

    try:
        data = json.loads(resp_body)
        return DelegationResponse.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise BackupClientError(
            f"Malformed response from backup service: {exc}"
        ) from exc


def is_delegation_available() -> bool:
    """Check whether the A-side has enough config to attempt delegation.

    Returns True if both the backup URL and token are set.  Does NOT
    check whether the remote service is actually reachable.
    """
    return bool(get_backup_service_url() and get_configured_token())
