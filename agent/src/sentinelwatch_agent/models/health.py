"""
Health and Error Models for SentinelWatch Agent.
"""

from datetime import datetime, timezone
from typing import Any, Optional, Dict, List
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class CollectorStatus(str, Enum):
    """Collector health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


class CollectionError(BaseModel):
    """Collection error record."""

    model_config = ConfigDict(extra="forbid")

    collector_name: str = Field(..., description="Name of the collector that errored")
    error_type: str = Field(..., description="Type of error (e.g., AccessDenied, ProcessTerminated)")
    error_message: str = Field(..., description="Human-readable error message")
    error_details: Optional[str] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Error timestamp")
    is_recoverable: bool = Field(True, description="Whether the error is recoverable")
    retry_count: int = Field(0, description="Number of retry attempts")


class CollectorStats(BaseModel):
    """Statistics for a single collector."""

    model_config = ConfigDict(extra="forbid")

    collector_name: str = Field(..., description="Collector name")
    status: CollectorStatus = Field(CollectorStatus.UNKNOWN, description="Current status")

    # Run statistics
    runs_count: int = Field(0, description="Total number of collection runs")
    successful_runs: int = Field(0, description="Successful collection runs")
    failed_runs: int = Field(0, description="Failed collection runs")
    skipped_runs: int = Field(0, description="Skipped runs (e.g., no data)")

    # Timing
    last_run_at: Optional[datetime] = Field(None, description="Last run timestamp")
    last_success_at: Optional[datetime] = Field(None, description="Last successful run timestamp")
    last_error_at: Optional[datetime] = Field(None, description="Last error timestamp")
    avg_duration_ms: float = Field(0.0, description="Average collection duration in milliseconds")
    max_duration_ms: float = Field(0.0, description="Maximum collection duration in milliseconds")
    total_duration_ms: float = Field(0.0, description="Total collection duration in milliseconds")

    # Error tracking
    total_errors: int = Field(0, description="Total errors encountered")
    consecutive_errors: int = Field(0, description="Consecutive errors")
    last_error: Optional[CollectionError] = Field(None, description="Last error details")

    # Data statistics
    records_collected: int = Field(0, description="Total records collected")
    records_sent: int = Field(0, description="Records successfully sent")
    records_failed: int = Field(0, description="Records failed to send")

    def record_success(self, duration_ms: float, record_count: int) -> None:
        """Record a successful collection run."""
        self.runs_count += 1
        self.successful_runs += 1
        self.last_run_at = datetime.now(timezone.utc)
        self.last_success_at = datetime.now(timezone.utc)
        self.consecutive_errors = 0
        self.total_duration_ms += duration_ms
        self.avg_duration_ms = self.total_duration_ms / self.runs_count
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.records_collected += record_count
        self.status = CollectorStatus.HEALTHY

    def record_error(self, error: CollectionError, duration_ms: float) -> None:
        """Record a failed collection run."""
        self.runs_count += 1
        self.failed_runs += 1
        self.last_run_at = datetime.now(timezone.utc)
        self.last_error_at = datetime.now(timezone.utc)
        self.consecutive_errors += 1
        self.total_errors += 1
        self.total_duration_ms += duration_ms
        self.avg_duration_ms = self.total_duration_ms / self.runs_count
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.last_error = error
        if self.consecutive_errors >= 3:
            self.status = CollectorStatus.UNHEALTHY
        elif self.consecutive_errors >= 1:
            self.status = CollectorStatus.DEGRADED

    def record_skip(self) -> None:
        """Record a skipped collection run."""
        self.runs_count += 1
        self.skipped_runs += 1
        self.last_run_at = datetime.now(timezone.utc)


class AgentHealth(BaseModel):
    """Overall agent health status."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Agent identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = Field(..., description="Agent version")

    # Overall status
    status: CollectorStatus = Field(CollectorStatus.HEALTHY, description="Overall health status")
    is_healthy: bool = Field(True, description="Whether agent is considered healthy")

    # System metrics
    cpu_percent: float = Field(0.0, ge=0.0, le=100.0, description="Agent CPU usage percentage")
    memory_bytes: int = Field(0, ge=0, description="Agent memory usage in bytes")
    memory_percent: float = Field(0.0, ge=0.0, le=100.0, description="Agent memory usage percentage")
    disk_usage_bytes: int = Field(0, ge=0, description="Disk usage for agent data")
    disk_usage_percent: float = Field(0.0, ge=0.0, le=100.0, description="Disk usage percentage")

    # Network
    bytes_sent: int = Field(0, ge=0, description="Total bytes sent")
    bytes_received: int = Field(0, ge=0, description="Total bytes received")

    # Collector stats
    collectors: Dict[str, CollectorStats] = Field(default_factory=dict)

    # Queue metrics
    queue_depth: int = Field(0, description="Current queue depth (unsent batches)")
    batches_sent: int = Field(0, description="Total batches sent")
    batches_failed: int = Field(0, description="Total batches failed")
    events_sent: int = Field(0, description="Total events sent")
    events_rejected: int = Field(0, description="Total events rejected by backend")

    # Communication
    last_heartbeat_at: Optional[datetime] = Field(None, description="Last successful heartbeat")
    last_config_poll_at: Optional[datetime] = Field(None, description="Last successful config poll")
    config_version: int = Field(0, description="Current configuration version")

    # Uptime
    uptime_seconds: float = Field(0.0, description="Agent uptime in seconds")

    def get_collector(self, name: str) -> CollectorStats:
        """Get or create collector stats."""
        if name not in self.collectors:
            self.collectors[name] = CollectorStats(collector_name=name)
        return self.collectors[name]

    def update_overall_status(self) -> None:
        """Update overall health based on collectors."""
        if not self.collectors:
            self.status = CollectorStatus.UNKNOWN
            self.is_healthy = True
            return

        unhealthy_count = sum(1 for c in self.collectors.values() if c.status == CollectorStatus.UNHEALTHY)
        degraded_count = sum(1 for c in self.collectors.values() if c.status == CollectorStatus.DEGRADED)

        if unhealthy_count > 0:
            self.status = CollectorStatus.UNHEALTHY
            self.is_healthy = False
        elif degraded_count > 0:
            self.status = CollectorStatus.DEGRADED
            self.is_healthy = True
        else:
            self.status = CollectorStatus.HEALTHY
            self.is_healthy = True


class RetryPolicy(BaseModel):
    """Retry policy configuration."""

    model_config = ConfigDict(extra="forbid")

    max_retries: int = Field(3, ge=0, description="Maximum retry attempts")
    base_delay_seconds: float = Field(1.0, ge=0.0, description="Base delay in seconds")
    max_delay_seconds: float = Field(60.0, ge=0.0, description="Maximum delay in seconds")
    exponential_base: float = Field(2.0, ge=1.0, description="Exponential backoff base")
    jitter: bool = Field(True, description="Add random jitter to delay")

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number."""
        import random
        delay = min(self.base_delay_seconds * (self.exponential_base ** attempt), self.max_delay_seconds)
        if self.jitter:
            delay *= (0.5 + random.random())  # 50-150% of calculated delay
        return delay


class CircuitBreakerState(BaseModel):
    """Circuit breaker state for a remote endpoint."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(..., description="Endpoint identifier")
    failure_count: int = Field(0, description="Consecutive failures")
    success_count: int = Field(0, description="Consecutive successes")
    last_failure_at: Optional[datetime] = Field(None, description="Last failure timestamp")
    last_success_at: Optional[datetime] = Field(None, description="Last success timestamp")
    is_open: bool = Field(False, description="Whether circuit is open (blocking requests)")
    opened_at: Optional[datetime] = Field(None, description="When circuit was opened")

    def record_success(self) -> None:
        """Record a successful request."""
        self.success_count += 1
        self.failure_count = 0
        self.last_success_at = datetime.now(timezone.utc)
        if self.success_count >= 5 and self.is_open:
            # Close circuit after 5 consecutive successes
            self.is_open = False
            self.opened_at = None

    def record_failure(self, threshold: int = 5) -> None:
        """Record a failed request."""
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_at = datetime.now(timezone.utc)
        if self.failure_count >= threshold and not self.is_open:
            self.is_open = True
            self.opened_at = datetime.now(timezone.utc)

    def can_request(self, reset_timeout_seconds: float = 60.0) -> bool:
        """Check if request can proceed."""
        if not self.is_open:
            return True
        # Check if reset timeout has passed
        if self.opened_at:
            elapsed = (datetime.now(timezone.utc) - self.opened_at).total_seconds()
            if elapsed >= reset_timeout_seconds:
                # Half-open state - allow one request
                return True
        return False
