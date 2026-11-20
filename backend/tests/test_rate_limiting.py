from sentinelwatch_backend.config import RateLimitingConfig
from sentinelwatch_backend.security.rate_limit import TokenBucketRateLimiter, _rate_limit_for_path
from sentinelwatch_backend.security.rate_limit import RateLimitMiddleware
from sentinelwatch_backend.main import create_app
import time


def test_token_bucket_enforces_burst_and_refills_over_time():
    limiter = TokenBucketRateLimiter()

    assert limiter.consume("auth", "client", limit_per_minute=2, burst=2, now=0) == (True, 0)
    assert limiter.consume("auth", "client", limit_per_minute=2, burst=2, now=0) == (True, 0)
    assert limiter.consume("auth", "client", limit_per_minute=2, burst=2, now=0) == (False, 30)
    assert limiter.consume("auth", "client", limit_per_minute=2, burst=2, now=30) == (True, 0)


def test_rate_limit_keys_are_separated_by_client_and_category():
    limiter = TokenBucketRateLimiter()
    assert limiter.consume("auth", "client-a", 1, 1, now=0)[0]
    assert not limiter.consume("auth", "client-a", 1, 1, now=0)[0]
    assert limiter.consume("agent", "client-a", 1, 1, now=0)[0]
    assert limiter.consume("auth", "client-b", 1, 1, now=0)[0]


def test_sensitive_routes_receive_their_configured_rate_class():
    config = RateLimitingConfig()

    assert _rate_limit_for_path("/api/v1/auth/login", config)[0] == "auth"
    assert _rate_limit_for_path("/api/v1/agent/v1/register", config)[0] == "register"
    assert _rate_limit_for_path("/api/v1/agent/v1/telemetry", config)[0] == "agent"
    assert _rate_limit_for_path("/api/v1/telemetry/processes", config)[0] == "default"
    assert _rate_limit_for_path("/health", config) is None


def test_middleware_returns_429_with_retry_after_when_bucket_is_empty():
    from types import SimpleNamespace

    config = RateLimitingConfig(auth_limit=1, auth_burst=1)
    limiter = TokenBucketRateLimiter()
    limiter.consume("auth", "127.0.0.1", 1, 1, now=time.monotonic())
    middleware = RateLimitMiddleware(lambda scope, receive, send: None, config, limiter)
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/v1/auth/login"),
        method="POST",
        client=SimpleNamespace(host="127.0.0.1"),
    )

    coroutine = middleware.dispatch(request, lambda _request: None)
    try:
        coroutine.send(None)
    except StopIteration as completed:
        response = completed.value
    else:
        raise AssertionError("The rate-limit rejection path unexpectedly waited")

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_rate_limit_middleware_is_installed_in_application():
    from sentinelwatch_backend.config import BackendConfig

    app = create_app(BackendConfig())

    assert any(middleware.cls is RateLimitMiddleware for middleware in app.user_middleware)
