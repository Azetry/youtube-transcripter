"""Input signature generation for exact-match job reuse.

Generates a deterministic hash of normalized job inputs so that
identical requests can be detected and reused. The signature
includes a strategy version to invalidate cached results when
processing logic changes.
"""

import hashlib
import json
from typing import Optional

# Bump this when transcription/correction logic changes materially,
# to invalidate previously cached results.
STRATEGY_VERSION = "v1"


def compute_input_signature(
    url: str,
    language: Optional[str] = None,
    skip_correction: bool = False,
    custom_terms: Optional[list[str]] = None,
    speaker_attribution: bool = False,
) -> str:
    """Compute a deterministic signature for job inputs.

    The signature is a hex SHA-256 digest of the canonicalized inputs
    plus the strategy version.
    """
    # Normalize inputs for deterministic hashing
    normalized = {
        "strategy_version": STRATEGY_VERSION,
        "url": _normalize_url(url),
        "language": language or "",
        "skip_correction": skip_correction,
        "custom_terms": sorted(custom_terms) if custom_terms else [],
        "speaker_attribution": speaker_attribution,
    }
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_url(url: str) -> str:
    """Extract canonical video identifier from YouTube URL.

    Strips tracking parameters and normalizes to a consistent form.
    For now, just strips whitespace and trailing slashes.
    A more robust implementation could extract the video ID.
    """
    return url.strip().rstrip("/")
