"""Enrollment-token lifetimes stay bounded at creation and update time."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinelwatch_backend.api.v1.enrollment_tokens import (
    DEFAULT_ENROLLMENT_TTL_DAYS,
    MAX_ENROLLMENT_TTL_DAYS,
    EnrollmentTokenCreate,
    EnrollmentTokenUpdate,
)
from sentinelwatch_backend.models.enrollment_token import (
    EnrollmentToken,
    EnrollmentTokenStatus,
)


def test_create_token_lifetime_defaults_to_short_window_and_caps_at_thirty_days():
    assert EnrollmentTokenCreate(name="default").expires_in_days is None
    assert DEFAULT_ENROLLMENT_TTL_DAYS == 7
    assert EnrollmentTokenCreate(name="maximum", expires_in_days=30).expires_in_days == 30

    with pytest.raises(ValidationError):
        EnrollmentTokenCreate(name="too-long", expires_in_days=31)


def test_token_update_expiration_must_be_future_and_within_thirty_days():
    expiration = datetime.now(timezone.utc) + timedelta(days=MAX_ENROLLMENT_TTL_DAYS, seconds=-1)
    assert EnrollmentTokenUpdate(expires_at=expiration).expires_at == expiration

    with pytest.raises(ValidationError):
        EnrollmentTokenUpdate(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(ValidationError):
        EnrollmentTokenUpdate(expires_at=datetime.now(timezone.utc) + timedelta(days=31))


def test_expired_token_is_not_valid():
    token = EnrollmentToken(
        id="token-a",
        token_hash="0" * 64,
        token_prefix="12345678",
        organization_id="org-a",
        name="test",
        status=EnrollmentTokenStatus.ACTIVE,
        expires_at=datetime.now(timezone.utc) - timedelta(microseconds=1),
        used_count=0,
        max_uses=1,
    )

    assert token.is_valid() is False
