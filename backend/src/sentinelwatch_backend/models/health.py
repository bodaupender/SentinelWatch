"""
Health models for SentinelWatch Backend.
"""

from datetime import datetime, timezone
from typing import Any, Optional, Dict, List

from pydantic import BaseModel, Field, ConfigDict


class CollectorStatus(BaseModel):
    """Status of a telemetry collector."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Collector name")
    healthy: bool = Field(default=True, description="Whether collector is healthy")
    last_run: Optional[datetime] = Field(default=None, description="Last run timestamp")
    last_error: Optional[str] = Field(default=None, description="Last error message")
    runs_count: int = Field(default=0, ge=0, description="Total number of collection runs")
    errors_count: int = Field(default=0, ge=0, description="Total number of errors")
    avg_duration_ms: float = Field(default=0.0, ge=0.0, description="Average collection duration in milliseconds")


class AgentHealth(BaseModel):
    """Agent health status model."""
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Agent identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Health snapshot timestamp"
    )

    # System metrics
    cpu_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="CPU usage percentage")
    memory_mb: float = Field(default=0.0, ge=0.0, description="Memory usage in MB")
    memory_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="Memory usage percentage")
    disk_free_gb: float = Field(default=0.0, ge=0.0, description="Free disk space in GB")
    disk_total_gb: float = Field(default=0.0, ge=0.0, description="Total disk space in GB")
    disk_percent: float = Field(default=0.0, ge=0.0, le=100.0, description="Disk usage percentage")

    # Network metrics
    network_bytes_sent: int = Field(default=0, ge=0, description="Total bytes sent")
    network_bytes_recv: int = Field(default=0, ge=0, description="Total bytes received")
    network_packets_sent: int = Field(default=0, ge=0, description="Packets sent")
    network_packets_recv: int = Field(default=0, ge=0, description="Packets received")

    # Process metrics
    process_count: int = Field(default=0, ge=0, description="Number of processes")
    thread_count: int = Field(default=0, ge=0, description="Number of threads")
    open_files: int = Field(default=0, ge=0, description="Number of open files")
    open_connections: int = Field(default=0, ge=0, description="Number of open connections")

    # Collector status
    collectors: Dict[str, CollectorStatus] = Field(default_factory=dict, description="Collector statuses")

    # Queue metrics
    queue_depth: int = Field(default=0, ge=0, description="Unsent batch queue depth")
    batches_sent: int = Field(default=0, ge=0, description="Total batches sent")
    batches_failed: int = Field(default=0, ge=0, description="Total batches failed")
    events_sent: int = Field(default=0, ge=0, description="Total events sent")
    events_rejected: int = Field(default=0, ge=0, description="Total events rejected")

    # Communication
    last_heartbeat: Optional[datetime] = Field(default=None, description="Last successful heartbeat")
    last_config_poll: Optional[datetime] = Field(default=None, description="Last config poll")

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "memory_percent": self.memory_percent,
            "disk_free_gb": self.disk_free_gb,
            "disk_total_gb": self.disk_total_gb,
            "disk_percent": self.disk_percent,
            "network_bytes_sent": self.network_bytes_sent,
            "network_bytes_recv": self.network_bytes_recv,
            "network_packets_sent": self.network_packets_sent,
            "network_packets_recv": self.network_packets_recv,
            "process_count": self.process_count,
            "thread_count": self.thread_count,
            "open_files": self.open_files,
            "open_connections": self.open_connections,
            "collectors": {
                name: {
                    "healthy": c.healthy,
                    "last_run": c.last_run.isoformat() if c.last_run else None,
                    "last_error": c.last_error,
                    "runs_count": c.runs_count,
                    "errors_count": c.errors_count,
                    "avg_duration_ms": c.avg_duration_ms,
                }
                for name, c in self.collectors.items()
            },
            "queue_depth": self.queue_depth,
            "batches_sent": self.batches_sent,
            "batches_failed": self.batches_failed,
            "events_sent": self.events_sent,
            "events_rejected": self.events_rejected,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_config_poll": self.last_config_poll.isoformat() if self.last_config_poll else None,
        }

    def check_thresholds(self, config: "AgentConfig" = None) -> list[str]:
        """Check health metrics against configured thresholds."""
        alerts = []

        if config:
            if self.cpu_percent > config.health.cpu_threshold:
                alerts.append(f"CPU usage {self.cpu_percent:.1f}% exceeds threshold {config.health.cpu_threshold}%")

            if self.memory_mb > config.health.memory_threshold_mb:
                alerts.append(f"Memory usage {self.memory_mb:.1f}MB exceeds threshold {config.health.memory_threshold_mb}MB")

            if self.disk_free_gb < config.health.disk_threshold_gb:
                alerts.append(f"Disk free space {self.disk_free_gb:.1f}GB below threshold {config.health.disk_threshold_gb}GB")

            if self.queue_depth > config.health.queue_threshold:
                alerts.append(f"Queue depth {self.queue_depth} exceeds threshold {config.health.queue_threshold}")

            # Check collector health
            for name, collector in self.collectors.items():
                if not collector.healthy:
                    alerts.append(f"Collector '{name}' unhealthy: {collector.last_error}")

        return alerts


class HealthMonitor:
    """Monitors agent health metrics."""

    def __init__(self, config: Optional["AgentConfig"] = None):
        from .config import AgentConfig
        self.config = config or AgentConfig()
        self._start_time = datetime.now(timezone.utc)
        self._last_net_io = None
        self._collectors: Dict[str, CollectorStatus] = {}
        self._queue_depth = 0
        self._batches_sent = 0
        self._batches_failed = 0
        self._events_sent = 0
        self._events_rejected = 0
        self._last_heartbeat: Optional[datetime] = None
        self._last_config_poll: Optional[datetime] = None
        self._process = None

    def register_collector(self, name: str) -> CollectorStatus:
        """Register a collector for health tracking."""
        if name not in self._collectors:
            self._collectors[name] = CollectorStatus(name=name)
        return self._collectors[name]

    def record_collector_run(self, name: str, duration_ms: float, error: Optional[str] = None) -> None:
        """Record a collector execution."""
        collector = self._collectors.get(name)
        if collector:
            collector.runs_count += 1
            collector.last_run = datetime.now(timezone.utc)
            collector.avg_duration_ms = (
                (collector.avg_duration_ms * (collector.runs_count - 1) + duration_ms) / collector.runs_count
            )
            if error:
                collector.errors_count += 1
                collector.last_error = error
                collector.healthy = False
            else:
                collector.healthy = True

    def increment_queue(self, count: int = 1) -> None:
        """Increment queue depth."""
        self._queue_depth += count

    def decrement_queue(self, count: int = 1) -> None:
        """Decrement queue depth."""
        self._queue_depth = max(0, self._queue_depth - count)

    def record_batch_sent(self, event_count: int) -> None:
        """Record successful batch send."""
        self._batches_sent += 1
        self._events_sent += event_count
        self._last_heartbeat = datetime.now(timezone.utc)

    def record_batch_failed(self, event_count: int) -> None:
        """Record failed batch send."""
        self._batches_failed += 1
        self._events_rejected += event_count

    def record_config_poll(self) -> None:
        """Record configuration poll."""
        self._last_config_poll = datetime.now(timezone.utc)

    def collect(self, agent_id: str = "") -> "AgentHealth":
        """Collect current health metrics."""
        import psutil
        from datetime import timezone

        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Network metrics (delta since last collection)
        net_io = psutil.net_io_counters()
        net_sent = net_io.bytes_sent - self._last_net_io.bytes_sent if self._last_net_io else 0
        net_recv = net_io.bytes_recv - self._last_net_io.bytes_recv if self._last_net_io else 0
        net_packets_sent = net_io.packets_sent - self._last_net_io.packets_sent if self._last_net_io else 0
        net_packets_recv = net_io.packets_recv - self._last_net_io.packets_recv if self._last_net_io else 0
        self._last_net_io = net_io

        # Process metrics
        try:
            process_count = len(psutil.pids())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            process_count = 0

        try:
            thread_count = psutil.Process().num_threads()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            thread_count = 0

        try:
            open_files = len(psutil.Process().open_files())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            open_files = 0

        try:
            open_connections = len(psutil.Process().connections())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            open_connections = 0

        metrics = AgentHealth(
            agent_id=agent_id,
            timestamp=datetime.now(timezone.utc),
            cpu_percent=cpu_percent,
            memory_mb=memory.used / (1024 * 1024),
            memory_percent=memory.percent,
            disk_free_gb=disk.free / (1024 ** 3),
            disk_total_gb=disk.total / (1024 ** 3),
            disk_percent=(disk.used / disk.total) * 100 if disk.total > 0 else 0,
            network_bytes_sent=net_sent,
            network_bytes_recv=net_recv,
            network_packets_sent=net_packets_sent,
            network_packets_recv=net_packets_recv,
            process_count=process_count,
            thread_count=thread_count,
            open_files=open_files,
            open_connections=open_connections,
            collectors=dict(self._collectors),
            queue_depth=self._queue_depth,
            batches_sent=self._batches_sent,
            batches_failed=self._batches_failed,
            events_sent=self._events_sent,
            events_rejected=self._events_rejected,
            last_heartbeat=self._last_heartbeat,
            last_config_poll=self._last_config_poll,
            uptime_seconds=(datetime.now(timezone.utc) - self._start_time).total_seconds(),
        )

        # Log alerts if any thresholds exceeded
        if self.config and self.config.health.enabled:
            alerts = metrics.check_thresholds(self.config)
            for alert in alerts:
                logger.warning("health_threshold_exceeded", alert=alert, **metrics.to_dict())

        return metrics

    def get_collector_status(self, name: str) -> Optional[CollectorStatus]:
        """Get status of a specific collector."""
        return self._collectors.get(name)

    def is_healthy(self) -> bool:
        """Check if overall agent health is good."""
        metrics = self.collect()
        return len(metrics.check_thresholds(self.config)) == 0
