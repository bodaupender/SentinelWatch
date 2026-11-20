"""
SentinelWatch Agent Health Monitoring.

Collects and reports agent health metrics including CPU, memory, disk,
network, and collector status.
"""

import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import psutil

from .config import AgentConfig, get_config
from .logging import get_logger


logger = get_logger(__name__)


@dataclass
class CollectorStatus:
    """Status of a telemetry collector."""

    name: str
    healthy: bool = True
    last_run: Optional[datetime] = None
    last_error: Optional[str] = None
    runs_count: int = 0
    errors_count: int = 0
    avg_duration_ms: float = 0.0


@dataclass
class HealthMetrics:
    """Complete health metrics snapshot."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: str = ""
    version: str = "0.1.0"
    uptime_seconds: float = 0.0

    # System metrics
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    disk_percent: float = 0.0

    # Network metrics
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    network_packets_sent: int = 0
    network_packets_recv: int = 0

    # Process metrics
    process_count: Optional[int] = None
    thread_count: Optional[int] = None
    open_files: Optional[int] = None
    open_connections: Optional[int] = None

    # Collector status
    collectors: dict[str, CollectorStatus] = field(default_factory=dict)

    # Queue metrics
    queue_depth: int = 0
    batches_sent: int = 0
    batches_failed: int = 0
    events_sent: int = 0
    events_rejected: int = 0

    # Last successful backend communication
    last_heartbeat: Optional[datetime] = None
    last_config_poll: Optional[datetime] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
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

    def check_thresholds(self, config: AgentConfig) -> list[str]:
        """Check health metrics against configured thresholds."""
        alerts = []

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

    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or get_config()
        self._start_time = time.monotonic()
        self._last_net_io = psutil.net_io_counters()
        self._collectors: dict[str, CollectorStatus] = {}
        self._queue_depth = 0
        self._batches_sent = 0
        self._batches_failed = 0
        self._events_sent = 0
        self._events_rejected = 0
        self._last_heartbeat: Optional[datetime] = None
        self._last_config_poll: Optional[datetime] = None
        self._process = psutil.Process()

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

    def collect(self, agent_id: str = "") -> HealthMetrics:
        """Collect current health metrics."""
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(self.config.get_data_dir().anchor or "/"))

        # Network metrics (delta since last collection)
        net_io = psutil.net_io_counters()
        net_sent = net_io.bytes_sent - self._last_net_io.bytes_sent
        net_recv = net_io.bytes_recv - self._last_net_io.bytes_recv
        net_packets_sent = net_io.packets_sent - self._last_net_io.packets_sent
        net_packets_recv = net_io.packets_recv - self._last_net_io.packets_recv
        self._last_net_io = net_io

        # Process metrics
        try:
            process_count = len(psutil.pids())
        except (psutil.Error, OSError, RuntimeError):
            process_count = None

        try:
            thread_count = self._process.num_threads()
        except (psutil.Error, OSError, RuntimeError):
            thread_count = None

        try:
            open_files = len(self._process.open_files())
        except (psutil.Error, OSError, RuntimeError):
            open_files = None

        try:
            open_connections = len(self._process.connections())
        except (psutil.Error, OSError, RuntimeError):
            open_connections = None

        metrics = HealthMetrics(
            timestamp=datetime.now(timezone.utc),
            agent_id=agent_id,
            version="0.1.0",
            uptime_seconds=time.monotonic() - self._start_time,
            cpu_percent=cpu_percent,
            memory_mb=memory.used / (1024 * 1024),
            memory_percent=memory.percent,
            disk_free_gb=disk.free / (1024 * 1024 * 1024),
            disk_total_gb=disk.total / (1024 * 1024 * 1024),
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
        )

        # Log alerts if any thresholds exceeded
        if self.config.health.enabled:
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


def get_system_info() -> dict[str, Any]:
    """Get static system information."""
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "hostname": platform.node(),
        "boot_time": datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc).isoformat(),
        "cpu_count": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "total_memory_gb": psutil.virtual_memory().total / (1024**3),
    }
