"""
Tests for SentinelWatch Agent health monitoring.
"""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from sentinelwatch_agent.config import AgentConfig
from sentinelwatch_agent.health import CollectorStatus, HealthMetrics, HealthMonitor


class TestCollectorStatus:
    """Tests for CollectorStatus dataclass."""

    def test_default_values(self):
        """Test default collector status values."""
        status = CollectorStatus(name="test")

        assert status.name == "test"
        assert status.healthy is True
        assert status.last_run is None
        assert status.last_error is None
        assert status.runs_count == 0
        assert status.errors_count == 0
        assert status.avg_duration_ms == 0.0


class TestHealthMetrics:
    """Tests for HealthMetrics dataclass."""

    def test_default_values(self):
        """Test default health metrics values."""
        metrics = HealthMetrics()

        assert isinstance(metrics.timestamp, datetime)
        assert metrics.agent_id == ""
        assert metrics.version == "0.1.0"
        assert metrics.uptime_seconds == 0.0
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_mb == 0.0
        assert metrics.collectors == {}
        assert metrics.queue_depth == 0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = HealthMetrics(
            agent_id="test-agent",
            cpu_percent=50.0,
            memory_mb=100.0,
        )

        data = metrics.to_dict()

        assert data["agent_id"] == "test-agent"
        assert data["cpu_percent"] == 50.0
        assert data["memory_mb"] == 100.0
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)

    def test_to_dict_with_collectors(self):
        """Test to_dict includes collector status."""
        collector = CollectorStatus(name="test", healthy=False, last_error="timeout")
        metrics = HealthMetrics(collectors={"test": collector})

        data = metrics.to_dict()

        assert "test" in data["collectors"]
        assert data["collectors"]["test"]["healthy"] is False
        assert data["collectors"]["test"]["last_error"] == "timeout"

    def test_check_thresholds_cpu(self):
        """Test CPU threshold checking."""
        config = AgentConfig(health={"cpu_threshold": 80.0, "disk_threshold_gb": 0.0})
        metrics = HealthMetrics(cpu_percent=85.0, disk_free_gb=10.0)

        alerts = metrics.check_thresholds(config)

        assert any("CPU usage 85.0% exceeds threshold 80.0%" in a for a in alerts)

    def test_check_thresholds_memory(self):
        """Test memory threshold checking."""
        config = AgentConfig(health={"memory_threshold_mb": 500, "disk_threshold_gb": 0.0})
        metrics = HealthMetrics(memory_mb=600.0, disk_free_gb=10.0)

        alerts = metrics.check_thresholds(config)

        assert any("Memory usage 600.0MB exceeds threshold 500MB" in a for a in alerts)

    def test_check_thresholds_disk(self):
        """Test disk threshold checking."""
        config = AgentConfig(health={"disk_threshold_gb": 1.0})
        metrics = HealthMetrics(disk_free_gb=0.5)

        alerts = metrics.check_thresholds(config)

        assert any("Disk free space 0.5GB below threshold 1.0GB" in a for a in alerts)

    def test_check_thresholds_queue(self):
        """Test queue depth threshold checking."""
        config = AgentConfig(health={"queue_threshold": 1000, "disk_threshold_gb": 0.0})
        metrics = HealthMetrics(queue_depth=1500, disk_free_gb=10.0)

        alerts = metrics.check_thresholds(config)

        assert any("Queue depth 1500 exceeds threshold 1000" in a for a in alerts)

    def test_check_thresholds_collector_unhealthy(self):
        """Test unhealthy collector detection."""
        config = AgentConfig(health={"disk_threshold_gb": 0.0})
        collector = CollectorStatus(name="process", healthy=False, last_error="connection failed")
        metrics = HealthMetrics(collectors={"process": collector}, disk_free_gb=10.0)

        alerts = metrics.check_thresholds(config)

        assert any("Collector 'process' unhealthy: connection failed" in a for a in alerts)

    def test_check_thresholds_multiple(self):
        """Test multiple threshold violations."""
        config = AgentConfig(health={"cpu_threshold": 50.0, "memory_threshold_mb": 100, "disk_threshold_gb": 0.0})
        collector = CollectorStatus(name="service", healthy=False, last_error="timeout")
        metrics = HealthMetrics(
            cpu_percent=60.0,
            memory_mb=150.0,
            collectors={"service": collector},
            disk_free_gb=10.0,
        )

        alerts = metrics.check_thresholds(config)

        # Should have at least 3 alerts (CPU, memory, collector)
        assert len(alerts) >= 3


class TestHealthMonitor:
    """Tests for HealthMonitor class."""

    @pytest.fixture
    def config(self) -> AgentConfig:
        """Create test configuration."""
        return AgentConfig()

    @pytest.fixture
    def monitor(self, config: AgentConfig) -> HealthMonitor:
        """Create HealthMonitor instance."""
        return HealthMonitor(config)

    def test_register_collector(self, monitor: HealthMonitor):
        """Test collector registration."""
        collector = monitor.register_collector("test")

        assert collector.name == "test"
        assert collector.healthy is True

        # Registering again returns same instance
        collector2 = monitor.register_collector("test")
        assert collector is collector2

    def test_record_collector_run_success(self, monitor: HealthMonitor):
        """Test recording successful collector run."""
        monitor.register_collector("test")
        monitor.record_collector_run("test", 100.0)

        collector = monitor.get_collector_status("test")
        assert collector.runs_count == 1
        assert collector.avg_duration_ms == 100.0
        assert collector.healthy is True
        assert collector.last_error is None

    def test_record_collector_run_error(self, monitor: HealthMonitor):
        """Test recording failed collector run."""
        monitor.register_collector("test")
        monitor.record_collector_run("test", 50.0, error="timeout")

        collector = monitor.get_collector_status("test")
        assert collector.runs_count == 1
        assert collector.errors_count == 1
        assert collector.healthy is False
        assert collector.last_error == "timeout"

    def test_record_collector_run_avg_duration(self, monitor: HealthMonitor):
        """Test average duration calculation."""
        monitor.register_collector("test")
        monitor.record_collector_run("test", 100.0)
        monitor.record_collector_run("test", 200.0)
        monitor.record_collector_run("test", 300.0)

        collector = monitor.get_collector_status("test")
        assert collector.runs_count == 3
        assert collector.avg_duration_ms == 200.0  # (100+200+300)/3

    def test_increment_decrement_queue(self, monitor: HealthMonitor):
        """Test queue depth tracking."""
        assert monitor._queue_depth == 0

        monitor.increment_queue(5)
        assert monitor._queue_depth == 5

        monitor.increment_queue(3)
        assert monitor._queue_depth == 8

        monitor.decrement_queue(2)
        assert monitor._queue_depth == 6

        monitor.decrement_queue(10)  # Should not go negative
        assert monitor._queue_depth == 0

    def test_record_batch_sent(self, monitor: HealthMonitor):
        """Test recording successful batch send."""
        monitor.record_batch_sent(10)

        assert monitor._batches_sent == 1
        assert monitor._events_sent == 10
        assert monitor._last_heartbeat is not None

    def test_record_batch_failed(self, monitor: HealthMonitor):
        """Test recording failed batch send."""
        monitor.record_batch_failed(5)

        assert monitor._batches_failed == 1
        assert monitor._events_rejected == 5

    def test_record_config_poll(self, monitor: HealthMonitor):
        """Test recording config poll."""
        assert monitor._last_config_poll is None

        monitor.record_config_poll()

        assert monitor._last_config_poll is not None

    @patch("sentinelwatch_agent.health.psutil.cpu_percent")
    @patch("sentinelwatch_agent.health.psutil.virtual_memory")
    @patch("sentinelwatch_agent.health.psutil.disk_usage")
    @patch("sentinelwatch_agent.health.psutil.net_io_counters")
    @patch("sentinelwatch_agent.health.psutil.pids")
    def test_collect_metrics(
        self,
        mock_pids,
        mock_net_io,
        mock_disk,
        mock_memory,
        mock_cpu,
        monitor: HealthMonitor,
    ):
        """Test collecting health metrics."""
        # Mock psutil calls
        mock_cpu.return_value = 25.0
        mock_memory.return_value = MagicMock(used=512 * 1024 * 1024, percent=30.0)
        mock_disk.return_value = MagicMock(free=100 * 1024**3, total=500 * 1024**3, used=400 * 1024**3)
        mock_net_io.return_value = MagicMock(
            bytes_sent=1000, bytes_recv=2000, packets_sent=10, packets_recv=20
        )
        mock_pids.return_value = list(range(100))

        # Register a collector
        monitor.register_collector("test")

        metrics = monitor.collect(agent_id="test-agent")

        assert metrics.agent_id == "test-agent"
        assert metrics.cpu_percent == 25.0
        assert metrics.memory_mb == 512.0
        assert metrics.memory_percent == 30.0
        assert metrics.disk_free_gb == 100.0
        assert metrics.process_count == 100
        assert "test" in metrics.collectors

    @patch("sentinelwatch_agent.health.psutil.virtual_memory")
    @patch("sentinelwatch_agent.health.psutil.disk_usage")
    def test_is_healthy(self, mock_disk, mock_memory, monitor: HealthMonitor):
        """Test health check."""
        mock_memory.return_value = MagicMock(used=400 * 1024 * 1024, percent=30.0)
        mock_disk.return_value = MagicMock(free=100 * 1024**3, total=500 * 1024**3, used=400 * 1024**3)

        # Initially healthy with mocked resources (below all thresholds)
        assert monitor.is_healthy() is True

        # Add unhealthy collector
        monitor.register_collector("test")
        monitor.record_collector_run("test", 100.0, error="failed")

        assert monitor.is_healthy() is False

    def test_get_collector_status(self, monitor: HealthMonitor):
        """Test getting collector status."""
        monitor.register_collector("test")

        status = monitor.get_collector_status("test")
        assert status is not None
        assert status.name == "test"

        # Non-existent collector
        status = monitor.get_collector_status("nonexistent")
        assert status is None


class TestSystemInfo:
    """Tests for system info function."""

    @patch("sentinelwatch_agent.health.platform")
    @patch("sentinelwatch_agent.health.psutil")
    def test_get_system_info(self, mock_psutil, mock_platform):
        """Test getting system information."""
        from sentinelwatch_agent.health import get_system_info

        mock_platform.platform.return_value = "Windows-10-10.0.19045"
        mock_platform.system.return_value = "Windows"
        mock_platform.release.return_value = "10"
        mock_platform.version.return_value = "10.0.19045"
        mock_platform.machine.return_value = "AMD64"
        mock_platform.processor.return_value = "Intel64 Family 6 Model 158 Stepping 10"
        mock_platform.python_version.return_value = "3.12.0"
        mock_platform.node.return_value = "TEST-HOST"
        mock_psutil.boot_time.return_value = 1700000000
        mock_psutil.cpu_count.side_effect = lambda logical=True: 8 if logical else 4
        mock_psutil.virtual_memory.return_value = MagicMock(total=16 * 1024**3)

        info = get_system_info()

        assert info["platform"] == "Windows-10-10.0.19045"
        assert info["system"] == "Windows"
        assert info["hostname"] == "TEST-HOST"
        assert info["cpu_count"] == 8
        assert info["cpu_count_physical"] == 4
        assert info["total_memory_gb"] == 16.0
