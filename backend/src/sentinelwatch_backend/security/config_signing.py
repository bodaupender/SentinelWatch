"""Configuration signing and verification for SentinelWatch agents.

Agents receive their deployment configuration as a JSON blob plus an HMAC-SHA256
signature.  The signature covers the canonical (sorted) JSON representation so
that minor whitespace differences do not invalidate it, while still binding the
payload to the signing key.

The agent can verify that the configuration has not been tampered with on the
wire even when the transport is TLS only (no mTLS).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Optional


def sign_config(payload: Dict[str, Any], secret: bytes) -> str:
    """Return hex-HMAC-SHA256 over *payload* signed with *secret*.

    The payload is serialised with sorted keys and no extra whitespace so the
    canonical form is stable across Python versions.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(
    payload: Dict[str, Any],
    signature: str,
    secret: bytes,
) -> bool:
    """Verify that *signature* matches *payload* under *secret*.

    Uses constant-time comparison to avoid timing side-channels.
    Returns False (never raises) so callers can safely treat a bad signature
    as "configuration not trusted".
    """
    try:
        expected = sign_config(payload, secret)
    except Exception:
        return False
    return hmac.compare_digest(expected, signature)
