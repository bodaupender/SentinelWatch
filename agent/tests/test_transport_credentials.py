"""Credential refresh behavior for the long-running agent transport."""

import json
from sentinelwatch_agent.models.health import CollectionError
from sentinelwatch_agent.transport.http_client import HTTPClient, HTTPClientConfig


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status = status
        self.payload = payload or {}

    async def text(self):
        return json.dumps(self.payload)

    async def json(self):
        return self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class FakeSession:
    def __init__(self):
        self.request_headers = []
        self.requests = 0

    def request(self, _method, _url, **kwargs):
        self.request_headers.append(kwargs.get("headers", {}))
        self.requests += 1
        if self.requests == 1:
            return FakeResponse(401)
        return FakeResponse(200, {"status": "ok"})

    def post(self, _url, **kwargs):
        assert kwargs["json"]["refresh_token"] == "old-refresh"
        return FakeResponse(200, {
            "agent_token": "new-access",
            "agent_refresh_token": "new-refresh",
            "expires_in_seconds": 900,
        })


def _complete_without_io(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("Transport unit path unexpectedly waited for external I/O")


def test_401_rotates_credentials_persists_them_and_retries():
    client = HTTPClient(HTTPClientConfig(base_url="https://sentinel.example", api_prefix="/api/v1"))
    session = FakeSession()
    async def get_session():
        return session
    client._get_session = get_session
    persisted = []
    client.set_agent_credentials("old-access", "old-refresh", lambda access, refresh: persisted.append((access, refresh)))

    response, error = _complete_without_io(client._request_with_retry(
        "GET", "https://sentinel.example/api/v1/agent/v1/health"
    ))

    assert error is None
    assert response == {"status": "ok"}
    assert session.request_headers[0]["Authorization"] == "Bearer old-access"
    assert session.request_headers[1]["Authorization"] == "Bearer new-access"
    assert persisted == [("new-access", "new-refresh")]
    assert client._agent_refresh_token == "new-refresh"


def test_refresh_failure_returns_authentication_error():
    client = HTTPClient(HTTPClientConfig(base_url="https://sentinel.example", api_prefix="/api/v1"))

    class ExpiredSession:
        def request(self, *_args, **_kwargs):
            return FakeResponse(401)

        def post(self, *_args, **_kwargs):
            return FakeResponse(401)

    async def get_session():
        return ExpiredSession()
    client._get_session = get_session
    client.set_agent_credentials("old-access", "expired-refresh")
    response, error = _complete_without_io(
        client._request_with_retry("GET", "https://sentinel.example/api/v1/agent/v1/health")
    )

    assert response is None
    assert isinstance(error, CollectionError)
    assert error.error_type == "AuthenticationError"
