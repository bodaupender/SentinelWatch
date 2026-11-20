"""
HTTP Client for SentinelWatch Agent Telemetry Transport.

Handles HTTP/HTTPS communication with the backend API, including
per-agent bearer credentials, token refresh, retries, and circuit breaking.
"""

import asyncio
import json
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from ..config import AgentConfig, get_config
from ..logging import get_logger
from ..models import TelemetryBatch, ProcessTelemetry, ServiceTelemetry, StartupTelemetry, WindowsEventTelemetry
from ..models.health import RetryPolicy, CircuitBreakerState, CollectionError

# Optional zstd compression
try:
    import zstandard as zstd
    ZSTD_AVAILABLE = True
except ImportError:
    zstd = None
    ZSTD_AVAILABLE = False


class HTTPClientConfig:
    """Configuration for HTTP client."""

    def __init__(
        self,
        base_url: str = "https://api.sentinelwatch.local",
        api_prefix: str = "/api/v1",
        timeout: int = 30,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        verify_ssl: bool = True,
        ca_cert_path: Optional[str] = None,
        client_cert_path: Optional[str] = None,
        client_key_path: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.verify_ssl = verify_ssl
        self.ca_cert_path = ca_cert_path
        self.client_cert_path = client_cert_path
        self.client_key_path = client_key_path

    @classmethod
    def from_agent_config(cls, config: AgentConfig) -> "HTTPClientConfig":
        """Create config from agent configuration."""
        return cls(
            base_url=config.backend.url,
            api_prefix=config.backend.api_prefix,
            timeout=config.backend.timeout,
            max_retries=config.backend.max_retries,
            retry_base_delay=config.backend.retry_base_delay,
            retry_max_delay=config.backend.retry_max_delay,
            verify_ssl=True,
            ca_cert_path=config.tls.ca_file or None,
            client_cert_path=config.tls.cert_file or None,
            client_key_path=config.tls.key_file or None,
        )


class HTTPClient:
    """Async HTTP client for telemetry transport."""

    def __init__(self, config: HTTPClientConfig):
        self.config = config
        self.logger = get_logger("sentinelwatch_agent.transport.http_client")
        self._session: Optional[aiohttp.ClientSession] = None
        self._circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self._ssl_context: Optional[ssl.SSLContext] = None
        self._agent_token: Optional[str] = None
        self._agent_refresh_token: Optional[str] = None
        self._credential_refresh_callback = None

    def set_agent_token(self, token: str) -> None:
        """Set the short-lived signed credential returned during enrollment."""
        self._agent_token = token

    def set_agent_credentials(self, access_token: str, refresh_token: str, on_refresh=None) -> None:
        """Set access and rotating refresh credentials for a registered endpoint."""
        self._agent_token = access_token
        self._agent_refresh_token = refresh_token
        self._credential_refresh_callback = on_refresh

    @property
    def has_agent_credentials(self) -> bool:
        """Whether both credentials needed for authenticated long-running operation exist."""
        return bool(self._agent_token and self._agent_refresh_token)

    async def _refresh_agent_credentials(self) -> bool:
        if not self._agent_refresh_token:
            return False
        session = await self._get_session()
        url = f"{self.config.base_url}{self.config.api_prefix}/agent/v1/token/refresh"
        try:
            async with session.post(url, json={"refresh_token": self._agent_refresh_token}) as response:
                if response.status != 200:
                    return False
                payload = await response.json()
            access_token = payload.get("agent_token")
            refresh_token = payload.get("agent_refresh_token")
            if not access_token or not refresh_token:
                return False
            self.set_agent_credentials(access_token, refresh_token, self._credential_refresh_callback)
            if self._credential_refresh_callback:
                self._credential_refresh_callback(access_token, refresh_token)
            return True
        except Exception as exc:
            self.logger.warning("agent_token_refresh_failed", error=str(exc))
            return False

    async def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context with client certificates."""
        if self._ssl_context:
            return self._ssl_context

        context = ssl.create_default_context()
        context.check_hostname = self.config.verify_ssl
        context.verify_mode = ssl.CERT_REQUIRED if self.config.verify_ssl else ssl.CERT_NONE

        # Load CA certificate if provided
        if self.config.ca_cert_path and Path(self.config.ca_cert_path).exists():
            context.load_verify_locations(self.config.ca_cert_path)

        # Load client certificate and key if provided
        if self.config.client_cert_path and self.config.client_key_path:
            cert_path = Path(self.config.client_cert_path)
            key_path = Path(self.config.client_key_path)
            if cert_path.exists() and key_path.exists():
                context.load_cert_chain(cert_path, key_path)
            else:
                self.logger.warning("client_cert_or_key_not_found")

        self._ssl_context = context
        return context

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            ssl_context = await self._create_ssl_context()

            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )

            timeout = aiohttp.ClientTimeout(
                total=self.config.timeout,
                connect=10,
                sock_read=self.config.timeout,
            )

            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": f"SentinelWatch-Agent/0.1.0",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_circuit_breaker(self, endpoint: str) -> CircuitBreakerState:
        """Get or create circuit breaker for endpoint."""
        if endpoint not in self._circuit_breakers:
            self._circuit_breakers[endpoint] = CircuitBreakerState(endpoint=endpoint)
        return self._circuit_breakers[endpoint]

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[CollectionError]]:
        """Make HTTP request with retry logic and circuit breaker."""
        endpoint = url
        circuit_breaker = self._get_circuit_breaker(endpoint)

        # Check circuit breaker
        if not circuit_breaker.can_request():
            return None, CollectionError(
                collector_name="http_client",
                error_type="CircuitBreakerOpen",
                error_message=f"Circuit breaker open for {endpoint}",
                is_recoverable=True,
            )

        last_error: Optional[Exception] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                session = await self._get_session()

                request_headers = dict(headers or {})
                if self._agent_token and not url.endswith(("/register", "/token/refresh")):
                    request_headers["Authorization"] = f"Bearer {self._agent_token}"
                if data is not None:
                    request_headers["Content-Type"] = "application/octet-stream"
                    request_headers["Content-Encoding"] = "zstd"

                async with session.request(
                    method,
                    url,
                    json=json_data,
                    data=data,
                    headers=request_headers,
                ) as response:
                    response_text = await response.text()

                    if 200 <= response.status < 300:
                        circuit_breaker.record_success()
                        if response_text:
                            try:
                                return json.loads(response_text), None
                            except json.JSONDecodeError:
                                return {"status": "ok", "raw": response_text}, None
                        return {"status": "ok"}, None

                    elif response.status == 429:
                        # Rate limited
                        retry_after = int(response.headers.get("Retry-After", "1"))
                        error = CollectionError(
                            collector_name="http_client",
                            error_type="RateLimited",
                            error_message=f"Rate limited by backend, retry after {retry_after}s",
                            is_recoverable=True,
                        )
                        if attempt < self.config.max_retries:
                            await asyncio.sleep(retry_after)
                            continue
                        return None, error

                    elif response.status == 401:
                        if not url.endswith("/token/refresh") and await self._refresh_agent_credentials():
                            continue
                        # Authentication error
                        circuit_breaker.record_failure()
                        return None, CollectionError(
                            collector_name="http_client",
                            error_type="AuthenticationError",
                            error_message="Authentication failed (401)",
                            is_recoverable=False,
                        )

                    elif response.status == 403:
                        # Forbidden
                        circuit_breaker.record_failure()
                        return None, CollectionError(
                            collector_name="http_client",
                            error_type="ForbiddenError",
                            error_message="Access forbidden (403)",
                            is_recoverable=False,
                        )

                    elif 500 <= response.status < 600:
                        # Server error - retry
                        circuit_breaker.record_failure()
                        last_error = Exception(f"HTTP {response.status}: {response_text}")
                        self.logger.warning(
                            "backend_server_error",
                            status=response.status,
                            attempt=attempt + 1,
                            url=url,
                        )
                    else:
                        # Client error - don't retry
                        circuit_breaker.record_failure()
                        return None, CollectionError(
                            collector_name="http_client",
                            error_type=f"HTTP{response.status}",
                            error_message=f"HTTP {response.status}: {response_text}",
                            is_recoverable=False,
                        )

            except asyncio.TimeoutError:
                last_error = Exception("Request timeout")
                self.logger.warning("request_timeout", attempt=attempt + 1, url=url)
            except aiohttp.ClientConnectorError as e:
                last_error = e
                self.logger.warning("connection_error", attempt=attempt + 1, url=url, error=str(e))
            except Exception as e:
                last_error = e
                # aiohttp exceptions retain request/response objects, including the
                # Authorization header. Do not serialize exception locals/tracebacks.
                self.logger.error("unexpected_request_error", error_type=type(e).__name__)

            # Wait before retry
            if attempt < self.config.max_retries:
                delay = min(
                    self.config.retry_base_delay * (2 ** attempt),
                    self.config.retry_max_delay,
                )
                await asyncio.sleep(delay)

        # All retries exhausted
        circuit_breaker.record_failure()
        return None, CollectionError(
            collector_name="http_client",
            error_type=type(last_error).__name__ if last_error else "UnknownError",
            error_message=f"Request failed after {self.config.max_retries + 1} attempts: {last_error}",
            is_recoverable=True,
        )

    async def send_telemetry_batch(
        self,
        batch: TelemetryBatch,
        compress: bool = True,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[CollectionError]]:
        """Send one JSON telemetry batch to the authenticated agent endpoint."""
        url = f"{self.config.base_url}{self.config.api_prefix}/agent/v1/telemetry"
        records_json = [record.model_dump(mode="json") for record in batch.records]
        payload = {
            "agent_id": batch.agent_id,
            "telemetry_type": batch.telemetry_type,
            "batch": records_json,
            "compressed": False,
            "sequence": min((record.sequence for record in batch.records), default=0),
        }
        return await self._request_with_retry("POST", url, json_data=payload)

    async def send_heartbeat(
        self,
        agent_id: str,
        health_data: Dict[str, Any],
        version: str = "0.1.0",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[CollectionError]]:
        """Send agent heartbeat to backend."""
        url = f"{self.config.base_url}{self.config.api_prefix}/agent/v1/heartbeat"

        payload = {
            "agent_id": agent_id,
            "health": health_data,
            "version": version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return await self._request_with_retry("POST", url, json_data=payload)

    async def register_agent(
        self,
        enrollment_token: str,
        machine_guid: str,
        hostname: str,
        os_version: str,
        agent_version: str,
        csr_pem: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[CollectionError]]:
        """Register agent with backend."""
        url = f"{self.config.base_url}{self.config.api_prefix}/agent/v1/register"

        payload = {
            "enrollment_token": enrollment_token,
            "machine_guid": machine_guid,
            "hostname": hostname,
            "os_version": os_version,
            "agent_version": agent_version,
            "csr": csr_pem,
        }

        return await self._request_with_retry("POST", url, json_data=payload)

    async def get_agent_config(
        self,
        agent_id: str,
        current_config_version: int = 0,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[CollectionError]]:
        """Poll for configuration updates using the agent credential."""
        url = f"{self.config.base_url}{self.config.api_prefix}/agent/v1/config/poll"
        return await self._request_with_retry(
            "POST", url, json_data={
                "agent_id": agent_id,
                "current_config_version": current_config_version,
            }
        )

    async def health_check(self) -> Tuple[Optional[Dict[str, Any]], Optional[CollectionError]]:
        """Check backend health."""
        url = f"{self.config.base_url}/health"
        return await self._request_with_retry("GET", url)
