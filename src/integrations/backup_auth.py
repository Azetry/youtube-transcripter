"""Bearer-token authentication for internal backup-service delegation.

Unit H7a: minimal shared-secret auth for same-LAN HTTP delegation.
The token is read from the BACKUP_SERVICE_TOKEN environment variable.

This module provides:
  1. Token retrieval from env.
  2. Request-header construction (for the caller side).
  3. Token validation (for the backup-service side).

Security notes:
  - Internal network only — not designed for public internet.
  - Single shared bearer token — no per-user or per-service identity.
  - Future iterations may add HMAC signing or mTLS.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

# Environment variable name for the shared bearer token.
BACKUP_TOKEN_ENV = "BACKUP_SERVICE_TOKEN"


def get_configured_token() -> Optional[str]:
    """Return the configured backup-service token, or None if unset."""
    token = os.environ.get(BACKUP_TOKEN_ENV, "").strip()
    return token if token else None


def build_auth_header(token: str) -> dict[str, str]:
    """Build an Authorization header dict for outbound requests."""
    return {"Authorization": f"Bearer {token}"}


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """Extract the token from an Authorization header value.

    Returns the token string if the header is a valid Bearer token,
    or None otherwise.
    """
    if not authorization_header:
        return None
    parts = authorization_header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def validate_request_token(
    authorization_header: Optional[str],
    *,
    expected_token: Optional[str] = None,
) -> bool:
    """Validate an incoming request's bearer token.

    Args:
        authorization_header: The raw Authorization header value.
        expected_token: The expected token. If None, reads from env.

    Returns:
        True if the token matches, False otherwise.
    """
    if expected_token is None:
        expected_token = get_configured_token()

    if not expected_token:
        # No token configured — reject all requests.
        return False

    presented = extract_bearer_token(authorization_header)
    if not presented:
        return False

    # Constant-time comparison to prevent timing attacks.
    import hmac
    return hmac.compare_digest(presented, expected_token)
