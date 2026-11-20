"""Focused tests for revocable, per-agent bearer credentials."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
import re
import pytest

from sentinelwatch_backend.api.v1.agent_communication import (
    AGENT_ACCESS_TOKEN_TTL,
    AGENT_REFRESH_TOKEN_TTL,
    AgentTokenRefreshRequest,
    _rotate_agent_refresh_token,
    agent_credential_is_current,
    hash_agent_refresh_token,
)


def test_agent_token_must_match_current_credential_version():
    agent = SimpleNamespace(id="endpoint-a", credential_version=4, deleted_at=None)
    payload = {"sub": agent.id, "type": "agent", "credential_version": 4}
    assert agent_credential_is_current(payload, agent)
    assert not agent_credential_is_current({**payload, "credential_version": 3}, agent)


def test_revoked_or_wrong_subject_agent_token_is_rejected():
    agent = SimpleNamespace(id="endpoint-a", credential_version=0, deleted_at="revoked")
    payload = {"sub": agent.id, "type": "agent", "credential_version": 0}
    assert not agent_credential_is_current(payload, agent)
    agent.deleted_at = None
    assert not agent_credential_is_current({**payload, "sub": "endpoint-b"}, agent)
    assert not agent_credential_is_current({**payload, "type": "access"}, agent)


def test_agent_access_and_refresh_lifetimes_are_bounded():
    assert AGENT_ACCESS_TOKEN_TTL == timedelta(minutes=15)
    assert AGENT_REFRESH_TOKEN_TTL == timedelta(days=90)


def test_refresh_token_is_hashed_and_request_is_length_limited():
    raw_token = "r" * 64
    token_hash = hash_agent_refresh_token(raw_token)
    assert re.fullmatch(r"[0-9a-f]{64}", token_hash)
    assert token_hash != raw_token
    assert AgentTokenRefreshRequest(refresh_token=raw_token).refresh_token == raw_token
    with pytest.raises(ValueError):
        AgentTokenRefreshRequest(refresh_token="short")


def test_rotation_creates_only_a_hash_and_90_day_expiry():
    db = MagicMock()
    async def execute(_statement):
        return SimpleNamespace(scalar_one_or_none=lambda: None)
    db.execute = execute
    agent = SimpleNamespace(id="endpoint-a", credential_version=3)

    rotation = _rotate_agent_refresh_token(db, agent)
    try:
        rotation.send(None)
    except StopIteration as completed:
        raw_token = completed.value
    else:
        raise AssertionError("Refresh credential rotation unexpectedly awaited external I/O")

    credential = db.add.call_args.args[0]
    assert raw_token
    assert credential.token_hash == hash_agent_refresh_token(raw_token)
    assert raw_token not in credential.token_hash
    assert credential.credential_version == 3
    assert abs((credential.expires_at - datetime.now(timezone.utc) - AGENT_REFRESH_TOKEN_TTL).total_seconds()) < 2
