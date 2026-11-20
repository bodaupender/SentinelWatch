"""
Tests for SentinelWatch Agent telemetry models.
"""

import pytest
from datetime import datetime, timezone

from sentinelwatch_agent.models import (
    ProcessTelemetry,
    ServiceTelemetry,
    StartupTelemetry,
    WindowsEventTelemetry,
    AgentHealth,
    CollectorStats,
    CollectionError,
    CollectorStatus,
    TelemetryBatch,
    ProcessTreeNode,
    ProcessHashInfo,
    ProcessSignatureInfo,
    ServiceConfigInfo,
    ServiceHashInfo,
    ServiceSignatureInfo,
    StartupSource,
    EventLogChannel,
    RECOMMENDED_EVENT_IDS,
    TelemetryBase,
)


class TestProcessModels:
    """Tests for process telemetry models."""

    def test_process_telemetry_creation(self):
        """Test creating a process telemetry record."""
        record = ProcessTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=1,
            pid=1234,
            ppid=100,
            name="test.exe",
            exe="C:\\Windows\\System32\\test.exe",
            cmdline="test.exe --arg1",
            username="SYSTEM",
            cpu_percent=5.5,
            memory_percent=2.3,
        )

        assert record.pid == 1234
        assert record.name == "test.exe"
        assert record.cpu_percent == 5.5

    def test_process_telemetry_validation(self):
        """Test process telemetry field validation."""
        # Invalid PID
        with pytest.raises(ValueError):
            ProcessTelemetry(
                agent_id="test",
                collected_at=datetime.now(timezone.utc),
                sequence=1,
                pid=-1,  # Invalid
                ppid=0,
                name="test.exe",
            )

        # CPU percent out of range
        with pytest.raises(ValueError):
            ProcessTelemetry(
                agent_id="test",
                collected_at=datetime.now(timezone.utc),
                sequence=1,
                pid=1234,
                ppid=100,
                name="test.exe",
                cpu_percent=150.0,  # Invalid
            )

    def test_process_hash_info(self):
        """Test process hash info model."""
        hashes = ProcessHashInfo(
            sha256="a" * 64,
            md5="b" * 32,
            sha1="c" * 40,
        )
        assert hashes.sha256 == "a" * 64

    def test_process_signature_info(self):
        """Test process signature info model."""
        sig = ProcessSignatureInfo(
            is_signed=True,
            signer_name="Microsoft Corporation",
            is_trusted=True,
        )
        assert sig.is_signed is True
        assert sig.is_trusted is True

    def test_process_tree_node(self):
        """Test process tree node model."""
        child = ProcessTreeNode(
            pid=5678,
            ppid=1234,
            name="child.exe",
        )
        parent = ProcessTreeNode(
            pid=1234,
            ppid=100,
            name="parent.exe",
            children=[child],
        )
        assert len(parent.children) == 1
        assert parent.children[0].pid == 5678


class TestServiceModels:
    """Tests for service telemetry models."""

    def test_service_telemetry_creation(self):
        """Test creating a service telemetry record."""
        record = ServiceTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=1,
            name="TestService",
            display_name="Test Service",
            status="running",
            start_type="auto",
            service_type="own_process",
            binary_path="C:\\Windows\\System32\\test.exe",
        )

        assert record.name == "TestService"
        assert record.status == "running"

    def test_service_config_info(self):
        """Test service configuration audit info."""
        audit = ServiceConfigInfo(
            binary_path="C:\\Program Files\\Test\\service.exe",
            is_path_quoted=True,
            has_spaces_in_path=True,
            is_unquoted_with_spaces=False,
            path_exists=True,
        )
        assert audit.is_path_quoted is True
        assert audit.is_unquoted_with_spaces is False

    def test_service_status_conversion(self):
        """Test Windows service status conversion."""
        from sentinelwatch_agent.models import ServiceStatus
        assert ServiceStatus.from_windows_state(4) == "running"
        assert ServiceStatus.from_windows_state(1) == "stopped"
        assert ServiceStatus.from_windows_state(999) == "unknown"

    def test_service_start_type_conversion(self):
        """Test Windows service start type conversion."""
        from sentinelwatch_agent.models import ServiceStartType
        assert ServiceStartType.from_windows_start_type(2) == "auto"
        assert ServiceStartType.from_windows_start_type(4) == "disabled"


class TestStartupModels:
    """Tests for startup telemetry models."""

    def test_startup_telemetry_creation(self):
        """Test creating a startup telemetry record."""
        record = StartupTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=1,
            source=StartupSource.REGISTRY_RUN,
            name="TestStartup",
            command="C:\\Test\\app.exe",
            user_context="SYSTEM",
        )

        assert record.source == StartupSource.REGISTRY_RUN
        assert record.name == "TestStartup"

    def test_startup_source_enum(self):
        """Test startup source enum values."""
        assert StartupSource.REGISTRY_RUN.value == "registry_run"
        assert StartupSource.SCHEDULED_TASK.value == "scheduled_task"
        assert StartupSource.STARTUP_FOLDER_USER.value == "startup_folder_user"


class TestEventLogModels:
    """Tests for Windows event log telemetry models."""

    def test_windows_event_telemetry_creation(self):
        """Test creating an event log telemetry record."""
        record = WindowsEventTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=1,
            event_id=4688,
            record_id=12345,
            channel="Security",
            provider_name="Microsoft-Windows-Security-Auditing",
            level="information",
            event_timestamp=datetime.now(timezone.utc),
            computer="TEST-PC",
        )

        assert record.event_id == 4688
        assert record.channel == "Security"

    def test_event_log_channel_enum(self):
        """Test event log channel enum."""
        assert EventLogChannel.SECURITY.value == "Security"
        assert EventLogChannel.SYSTEM.value == "System"

    def test_recommended_event_ids(self):
        """Test recommended event IDs set."""
        assert 4688 in RECOMMENDED_EVENT_IDS  # Process Creation
        assert 4624 in RECOMMENDED_EVENT_IDS  # Logon
        assert 7045 in RECOMMENDED_EVENT_IDS  # Service Installed


class TestHealthModels:
    """Tests for health and error models."""

    def test_collection_error(self):
        """Test collection error model."""
        error = CollectionError(
            collector_name="process",
            error_type="AccessDenied",
            error_message="Cannot access process 1234",
            is_recoverable=True,
        )
        assert error.collector_name == "process"
        assert error.is_recoverable is True

    def test_collector_stats(self):
        """Test collector statistics model."""
        stats = CollectorStats(collector_name="process")
        stats.record_success(100.0, 50)
        assert stats.runs_count == 1
        assert stats.successful_runs == 1
        assert stats.records_collected == 50
        assert stats.status == CollectorStatus.HEALTHY

        stats.record_error(CollectionError(
            collector_name="process",
            error_type="Error",
            error_message="Test error",
        ), 50.0)
        assert stats.failed_runs == 1
        assert stats.consecutive_errors == 1

    def test_agent_health(self):
        """Test agent health model."""
        health = AgentHealth(
            agent_id="test-agent",
            version="0.1.0",
        )
        assert health.is_healthy is True

        # Add unhealthy collector
        health.collectors["process"] = CollectorStats(collector_name="process")
        health.collectors["process"].status = CollectorStatus.UNHEALTHY
        health.update_overall_status()
        assert health.is_healthy is False


class TestBaseModels:
    """Tests for base telemetry models."""

    def test_telemetry_base(self):
        """Test base telemetry model."""
        base = TelemetryBase(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=1,
        )
        assert base.agent_id == "test-agent"
        assert base.sequence == 1

    def test_telemetry_batch(self):
        """Test telemetry batch model."""
        batch = TelemetryBatch[ProcessTelemetry](
            agent_id="test-agent",
            telemetry_type="process",
            records=[],
        )
        assert batch.agent_id == "test-agent"
        assert batch.is_empty() is True

        record = ProcessTelemetry(
            agent_id="test-agent",
            collected_at=datetime.now(timezone.utc),
            sequence=1,
            pid=1234,
            ppid=100,
            name="test.exe",
        )
        batch.add_record(record)
        assert len(batch) == 1
        assert batch.is_empty() is False
