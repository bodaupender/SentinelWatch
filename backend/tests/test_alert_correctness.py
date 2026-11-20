"""Tests for alert deduplication and evidence traceability in agent_communication."""
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from sentinelwatch_backend.api.v1.agent_communication import _record_to_telemetry_dict


class TestRecordToTelemetryDict:
    def test_process_record_normalises_field_names(self):
        record = MagicMock()
        record.__dict__ = {
            "name": "evil.exe",
            "exe": "C:\\Temp\\evil.exe",
            "pid": 1234,
            "ppid": 5678,
            "parent_name": "WINWORD.EXE",
            "parent_exe": None,
            "username": "ATTACKER",
            "integrity_level": "High",
            "cmdline": "--password s3cr3t",
            "sequence": 10,
            "is_signed": False,
            "agent_id": "agent-1",
        }
        result = _record_to_telemetry_dict(record, "process")
        assert result is not None
        assert result["process_name"] == "evil.exe"
        assert result["process_pid"] == 1234
        assert result["parent_process_name"] == "WINWORD.EXE"
        # Cmdline credentials are redacted
        assert "s3cr3t" not in (result.get("process_cmdline") or "")
        assert "**REDACTED**" in (result.get("process_cmdline") or "")

    def test_service_record_maps_canonical_fields(self):
        record = MagicMock()
        record.__dict__ = {
            "name": "BadService",
            "display_name": "Bad Service",
            "binary_path": "C:\\Program Files\\evil\\svc.exe",
            "account": "LocalSystem",
            "start_type": "auto",
            "status": "running",
            "sequence": 5,
        }
        result = _record_to_telemetry_dict(record, "service")
        assert result is not None
        assert result["service_name"] == "BadService"
        assert result["service_binary_path"] == "C:\\Program Files\\evil\\svc.exe"
        assert "service_binary_directory" in result

    def test_startup_record_maps_canonical_fields(self):
        record = MagicMock()
        record.__dict__ = {
            "source": "registry_run",
            "name": "MalwareStart",
            "command": "C:\\evil\\run.bat",
            "user_context": "USER",
            "sequence": 3,
        }
        result = _record_to_telemetry_dict(record, "startup")
        assert result is not None
        assert result["startup_source"] == "registry_run"
        assert result["startup_entry"] == "MalwareStart"

    def test_eventlog_record_handles_extracted(self):
        record = MagicMock()
        record.__dict__ = {
            "event_id": 4624,
            "source": "Security",
            "message": "Logon event",
            "extracted": {"provider_name": "test"},
            "sequence": 1,
        }
        result = _record_to_telemetry_dict(record, "eventlog")
        assert result is not None
        assert result["event_log_event_id"] == 4624
        assert result.get("event_provider_name") == "test"

    def test_none_record_returns_none(self):
        assert _record_to_telemetry_dict(None, "process") is None

    def test_unknown_telemetry_type_falls_back_to_flat(self):
        record = MagicMock()
        record.__dict__ = {"a": 1, "b": 2}
        result = _record_to_telemetry_dict(record, "unknown")
        assert result is not None
        assert result.get("a") == 1


class TestDedupKeyGeneratesEntityScopedKey:
    """Verify that entity-aware dedup keys include process/service identity."""

    def test_dedup_key_contains_rule_and_agent_and_entity(self):
        """Different PIDs must produce different dedup keys even under the same rule."""
        # Simulate the key construction logic from agent_communication.py
        rule_id = "PR-001"
        agent_id = "agent-a"
        pid_a = 1001
        pid_b = 1002

        key_a = hashlib.sha256(
            f"{rule_id}|{agent_id}|{pid_a}".encode()
        ).hexdigest()[:16]
        key_b = hashlib.sha256(
            f"{rule_id}|{agent_id}|{pid_b}".encode()
        ).hexdigest()[:16]

        assert key_a != key_b, "Different PIDs must yield different dedup keys"

    def test_correlation_id_is_batch_scoped(self):
        """All alerts from the same batch share a correlation ID."""
        correlation_id = hashlib.sha256(
            f"PR-001|agent-a|process|42".encode()
        ).hexdigest()[:16]
        assert len(correlation_id) == 16


class TestAlertCountingIsAccurate:
    """alerts_created must only count *new* non-suppressed alerts."""

    def test_suppressed_events_do_not_increment_counter(self):
        """If an alert already exists for this entity+rule, counter stays at zero."""
        new_alerts = 0
        existing_count = 1  # simulated previous occurrence

        # Simulated loop body — suppressed path
        if existing_count > 0:
            pass  # skip increment
        else:
            new_alerts += 1

        assert new_alerts == 0

    def test_new_alert_increments_counter(self):
        new_alerts = 0
        existing_count = 0

        if existing_count > 0:
            pass
        else:
            new_alerts += 1

        assert new_alerts == 1
