"""Startup restores a long-term identity without retaining the enrollment token."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from sentinelwatch_agent.main import SentinelWatchAgent
from sentinelwatch_agent.transport.http_client import HTTPClient, HTTPClientConfig


def test_existing_identity_restores_credentials_without_enrollment_token():
    app = SentinelWatchAgent.__new__(SentinelWatchAgent)
    app.config = SimpleNamespace(agent=SimpleNamespace(id=None, private_key_pem=None))
    app.identity_manager = MagicMock()
    app._http_client = HTTPClient(HTTPClientConfig())
    identity = {
        "agent_id": "agent-a",
        "agent_token": "access-secret",
        "agent_refresh_token": "refresh-secret",
        "private_key_pem": "private-key",
    }

    assert app._activate_stored_credentials(identity)
    assert app.config.agent.id == "agent-a"
    assert app.config.agent.private_key_pem == "private-key"
    assert app._http_client.has_agent_credentials


def test_missing_refresh_credential_does_not_start_registered_identity():
    app = SentinelWatchAgent.__new__(SentinelWatchAgent)
    app.config = SimpleNamespace(agent=SimpleNamespace(id=None, private_key_pem=None))
    app.identity_manager = MagicMock()
    app._http_client = HTTPClient(HTTPClientConfig())

    assert not app._activate_stored_credentials({"agent_id": "agent-a", "agent_token": "access"})
    assert not app._http_client.has_agent_credentials
