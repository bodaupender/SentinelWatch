"""
Tests for SentinelWatch Agent collectors.

These tests use mocks to simulate Windows APIs and verify collector behavior.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime, timezone

from sentinelwatch_agent.config import AgentConfig
from sentinelwatch_agent.collectors import (
    ProcessCollector,
    ServiceCollector,
    StartupCollector,
    EventLogCollector,
)
from sentinelwatch_agent.collectors.process import _pid_changes, redact_sensitive_command_line
from sentinelwatch_agent.collectors import eventlog as eventlog_module
from sentinelwatch_agent.models import ProcessTelemetry, ServiceTelemetry, StartupTelemetry, WindowsEventTelemetry
from sentinelwatch_agent.models.health import CollectionError


class TestProcessCollector:
    """Tests for ProcessCollector."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AgentConfig(
            collection={"process": 30},
            process={
                "collect_cmdline": True,
                "collect_hashes": False,
                "collect_connections": True,
                "exclude_names": "System,Registry,smss.exe,csrss.exe,wininit.exe,services.exe,lsass.exe,fontdrvhost.exe",
            },
        )

    @pytest.fixture
    def collector(self, config):
        """Create process collector instance."""
        return ProcessCollector(config)

    def test_pid_changes_report_created_and_exited_processes(self):
        """Reconciliation compares complete snapshots, not a partial loop prefix."""
        created, exited = _pid_changes({10, 20}, {20, 30})

        assert created == {30}
        assert exited == {10}

    def test_command_line_redaction_obeys_enabled_setting(self):
        config = AgentConfig()
        raw = "worker.exe --password=top-secret"
        assert "top-secret" not in redact_sensitive_command_line(raw, config)

        config.redaction.enabled = False
        assert redact_sensitive_command_line(raw, config) == raw

    def test_collector_initialization(self, collector):
        """Test collector initializes correctly."""
        assert collector.name == "process"
        assert collector.get_collection_interval() == 30
        # Config normalizes to lowercase
        assert "system" in collector._excluded_names
        assert "smss.exe" in collector._excluded_names

    @pytest.mark.asyncio
    async def test_collect_with_mock_processes(self, collector):
        """Test collection with mocked psutil processes."""
        # Create mock process
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.name.return_value = "test.exe"
        mock_proc.exe.return_value = "C:\\Windows\\test.exe"
        mock_proc.cmdline.return_value = ["test.exe", "--arg"]
        mock_proc.username.return_value = "SYSTEM"
        mock_proc.create_time.return_value = 1700000000.0
        mock_proc.cpu_percent.return_value = 5.0
        mock_proc.memory_percent.return_value = 2.0
        mock_proc.memory_info.return_value = MagicMock(rss=1000000, vms=2000000)
        mock_proc.num_threads.return_value = 10
        mock_proc.status.return_value = "running"
        mock_proc.connections.return_value = []
        mock_proc.parent.return_value = None

        # Mock psutil.pids and psutil.Process
        with patch("psutil.pids", return_value=[1234]):
            with patch("psutil.Process", return_value=mock_proc):
                with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
                    # Configure mock responses for async calls
                    mock_to_thread.side_effect = [
                        1234,  # psutil.Process(pid)
                        "test.exe",  # name()
                        "C:\\Windows\\test.exe",  # exe()
                        ["test.exe", "--arg"],  # cmdline()
                        "SYSTEM",  # username()
                        1700000000.0,  # create_time()
                        5.0,  # cpu_percent()
                        2.0,  # memory_percent()
                        MagicMock(rss=1000000, vms=2000000),  # memory_info()
                        10,  # num_threads()
                        "running",  # status()
                        [],  # connections()
                        None,  # parent()
                    ]

                    result = await collector.collect()

        assert result.record_count >= 0  # May be 0 if excluded
        assert result.duration_ms >= 0


class TestServiceCollector:
    """Tests for ServiceCollector."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AgentConfig(
            collection={"service": 60},
            service={"collect_hashes": False, "include_stopped": True},
        )

    @pytest.fixture
    def collector(self, config):
        """Create service collector instance."""
        return ServiceCollector(config)

    def test_collector_initialization(self, collector):
        """Test collector initializes correctly."""
        assert collector.name == "service"
        assert collector.get_collection_interval() == 60


class TestStartupCollector:
    """Tests for StartupCollector."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AgentConfig(
            collection={"startup": 3600},
            startup={
                "registry": True,
                "scheduled_tasks": True,
                "startup_folders": True,
                "wmi_subscriptions": True,
            },
        )

    @pytest.fixture
    def collector(self, config):
        """Create startup collector instance."""
        return StartupCollector(config)

    def test_collector_initialization(self, collector):
        """Test collector initializes correctly."""
        assert collector.name == "startup"
        assert collector.get_collection_interval() == 3600


class TestEventLogCollector:
    """Tests for EventLogCollector."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AgentConfig(
            collection={"eventlog": 10},
            eventlog={
                "channels": ["Security", "System"],
                "event_ids": [4688, 4624, 7045],
                "max_events_per_poll": 100,
            },
        )

    @pytest.fixture
    def collector(self, config):
        """Create event log collector instance."""
        return EventLogCollector(config)

    def test_collector_initialization(self, collector):
        """Test collector initializes correctly."""
        assert collector.name == "eventlog"
        assert collector.get_collection_interval() == 10

    def test_unavailable_eventlog_api_degrades_only_this_collector(self, collector, monkeypatch):
        monkeypatch.setattr(eventlog_module, "win32evtlog", None)
        coroutine = collector.collect()
        with pytest.raises(StopIteration) as completed:
            coroutine.send(None)
        result = completed.value.value
        assert result.records == []
        assert result.errors[0].error_type == "WindowsEventLogUnavailable"


class TestCollectorBase:
    """Tests for base collector functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return AgentConfig()

    def test_collector_registration(self, config):
        """Test collector registers with health monitor."""
        collector = ProcessCollector(config)
        assert collector.stats is not None
        assert collector.stats.collector_name == "process"

    def test_collector_stats_recording(self, config):
        """Test collector stats are recorded correctly."""
        collector = ProcessCollector(config)

        # Record success
        collector.stats.record_success(100.0, 10)
        assert collector.stats.runs_count == 1
        assert collector.stats.successful_runs == 1
        assert collector.stats.records_collected == 10

        # Record error
        from sentinelwatch_agent.models.health import CollectionError
        error = CollectionError(
            collector_name="process",
            error_type="TestError",
            error_message="Test error",
        )
        collector.stats.record_error(error, 50.0)
        assert collector.stats.failed_runs == 1
        assert collector.stats.consecutive_errors == 1

    def test_collector_retry_policy(self, config):
        """Test collector retry logic."""
        from sentinelwatch_agent.models.health import RetryPolicy

        policy = RetryPolicy(max_retries=2, base_delay_seconds=0.01)
        collector = ProcessCollector(config, retry_policy=policy)

        assert collector.retry_policy.max_retries == 2
        assert collector.retry_policy.base_delay_seconds == 0.01

        # Test delay calculation
        delay = policy.get_delay(0)
        assert 0.005 <= delay <= 0.015  # With jitter

        delay = policy.get_delay(1)
        assert 0.01 <= delay <= 0.03


class TestBatching:
    """Tests for telemetry batching."""

    def test_batcher_creation(self):
        """Test batcher initialization."""
        from sentinelwatch_agent.transport import TelemetryBatcher, BatcherConfig
        from sentinelwatch_agent.models import ProcessTelemetry

        config = BatcherConfig(max_batch_size=10, max_batch_interval=1.0)
        batcher = TelemetryBatcher("process", "test-agent", config)

        assert batcher.telemetry_type == "process"
        assert batcher.agent_id == "test-agent"
        assert batcher.config.max_batch_size == 10

    @pytest.mark.asyncio
    async def test_batcher_add_and_flush(self):
        """Test adding records and flushing batch."""
        from sentinelwatch_agent.transport import TelemetryBatcher, BatcherConfig
        from sentinelwatch_agent.models import ProcessTelemetry
        from datetime import timezone

        config = BatcherConfig(max_batch_size=2, max_batch_interval=10.0)
        batcher = TelemetryBatcher("process", "test-agent", config)

        # Add first record
        record1 = ProcessTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=0,
            pid=1234,
            ppid=100,
            name="test1.exe",
        )
        await batcher.add(record1)
        assert batcher.buffer_size() == 1

        # Add second record - should trigger flush
        record2 = ProcessTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=0,
            pid=1235,
            ppid=100,
            name="test2.exe",
        )
        await batcher.add(record2)
        assert batcher.buffer_size() == 0  # Flushed

    @pytest.mark.asyncio
    async def test_multi_batcher(self):
        """Test multi-telemetry batcher."""
        from sentinelwatch_agent.transport import MultiTelemetryBatcher
        from sentinelwatch_agent.config import AgentConfig
        from sentinelwatch_agent.models import ProcessTelemetry, ServiceTelemetry

        config = AgentConfig()
        multi_batcher = MultiTelemetryBatcher("test-agent", config)

        # Add records to different batchers
        record1 = ProcessTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=0,
            pid=1234,
            ppid=100,
            name="test.exe",
        )
        await multi_batcher.add_record("process", record1)

        record2 = ServiceTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=0,
            name="TestService",
            status="running",
            start_type="auto",
            service_type="own_process",
        )
        await multi_batcher.add_record("service", record2)

        # Flush all
        batches = await multi_batcher.flush_all()
        assert "process" in batches
        assert "service" in batches
        assert len(batches["process"].records) == 1
        assert len(batches["service"].records) == 1


# Import datetime for tests
from datetime import datetime
