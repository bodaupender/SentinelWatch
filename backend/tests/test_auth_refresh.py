"""Refresh-token extraction compatibility tests."""

import pytest
from fastapi import HTTPException

from sentinelwatch_backend.api.v1.auth import _resolve_refresh_token


def test_refresh_body_token_takes_precedence_over_cookie():
    assert _resolve_refresh_token("body-token", "cookie-token") == "body-token"


def test_refresh_cookie_supports_browser_session_recovery():
    assert _resolve_refresh_token(None, "cookie-token") == "cookie-token"


def test_refresh_without_body_or_cookie_is_unauthorized():
    with pytest.raises(HTTPException) as error:
        _resolve_refresh_token(None, None)

    assert error.value.status_code == 401
