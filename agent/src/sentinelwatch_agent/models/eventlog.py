"""
Windows Event Log Telemetry Models for SentinelWatch Agent.
"""

from datetime import datetime, timezone
from typing import Any, Optional, Dict, List
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class EventLogChannel(str, Enum):
    """Standard Windows Event Log channels."""

    SECURITY = "Security"
    SYSTEM = "System"
    APPLICATION = "Application"
    SYSMON = "Microsoft-Windows-Sysmon/Operational"
    POWERSHELL = "Microsoft-Windows-PowerShell/Operational"
    WMI = "Microsoft-Windows-WMI-Activity/Operational"
    TERMINAL_SERVICES = "Microsoft-Windows-TerminalServices-LocalSessionManager/Operational"
    DEFENDER = "Microsoft-Windows-Windows Defender/Operational"


class EventLevel(str, Enum):
    """Event log levels."""

    LOG_ALWAYS = "log_always"
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"
    VERBOSE = "verbose"


class WindowsEventTelemetry(BaseModel):
    """Windows Event Log telemetry record."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Unique agent identifier")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = Field(..., description="Monotonically increasing sequence number")

    # Event identification
    event_id: int = Field(..., ge=0, le=65535, description="Event ID")
    record_id: int = Field(..., ge=0, description="Event record ID (unique per channel)")
    channel: str = Field(..., description="Event log channel name")
    provider_name: str = Field(..., description="Event provider name")
    provider_guid: Optional[str] = Field(None, description="Provider GUID")

    # Event metadata
    level: str = Field(..., description="Event level (critical, error, warning, information, verbose)")
    level_value: Optional[int] = Field(None, description="Numeric level value")
    task: Optional[int] = Field(None, description="Event task")
    opcode: Optional[int] = Field(None, description="Event opcode")
    keywords: Optional[str] = Field(None, description="Event keywords")
    keywords_value: Optional[int] = Field(None, description="Numeric keywords value")

    # Event timing
    event_timestamp: datetime = Field(..., description="Event timestamp (UTC)")

    # Event source
    computer: str = Field(..., description="Computer name where event originated")
    user_sid: Optional[str] = Field(None, description="User SID")
    user_name: Optional[str] = Field(None, description="User name")
    user_domain: Optional[str] = Field(None, description="User domain")

    # Event data
    message: Optional[str] = Field(None, max_length=65536, description="Rendered event message")
    raw_xml: Optional[str] = Field(None, max_length=262144, description="Raw event XML")

    # Extracted data (for common event IDs)
    extracted: Optional[Dict[str, Any]] = Field(None, description="Extracted structured data")

    # Process information (for process creation events)
    process_id: Optional[int] = Field(None, ge=0, description="Process ID from event")
    process_name: Optional[str] = Field(None, max_length=255, description="Process name from event")
    process_command_line: Optional[str] = Field(None, max_length=32768, description="Process command line from event")
    parent_process_id: Optional[int] = Field(None, ge=0, description="Parent process ID from event")
    parent_process_name: Optional[str] = Field(None, max_length=255, description="Parent process name from event")
    process_hash_sha256: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{64}$", description="Process executable hash")

    # Network information (for network events)
    source_ip: Optional[str] = Field(None, description="Source IP address")
    destination_ip: Optional[str] = Field(None, description="Destination IP address")
    source_port: Optional[int] = Field(None, ge=0, le=65535, description="Source port")
    destination_port: Optional[int] = Field(None, ge=0, le=65535, description="Destination port")
    protocol: Optional[str] = Field(None, description="Network protocol")

    # File information (for file events)
    file_path: Optional[str] = Field(None, max_length=4096, description="File path from event")
    file_hash_sha256: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{64}$", description="File hash")

    # Registry information (for registry events)
    registry_key: Optional[str] = Field(None, max_length=1024, description="Registry key path")
    registry_value: Optional[str] = Field(None, max_length=4096, description="Registry value name")
    registry_data: Optional[str] = Field(None, max_length=4096, description="Registry data")

    # Service information (for service events)
    service_name: Optional[str] = Field(None, max_length=255, description="Service name")
    service_display_name: Optional[str] = Field(None, max_length=255, description="Service display name")
    service_binary_path: Optional[str] = Field(None, max_length=4096, description="Service binary path")
    service_account: Optional[str] = Field(None, description="Service account")

    # Collection metadata
    collection_error: Optional[str] = Field(None, description="Error during collection if any")
    is_complete: bool = Field(True, description="Whether all fields were collected successfully")


# Important Event IDs to collect
SECURITY_EVENT_IDS = {
    4624: "Logon",
    4625: "Logon Failure",
    4634: "Logoff",
    4647: "User Initiated Logoff",
    4648: "Explicit Credential Logon",
    4672: "Special Logon",
    4688: "Process Creation",
    4689: "Process Termination",
    4697: "Service Installed",
    4698: "Scheduled Task Created",
    4699: "Scheduled Task Deleted",
    4700: "Scheduled Task Enabled",
    4701: "Scheduled Task Disabled",
    4702: "Scheduled Task Updated",
    4719: "Audit Policy Changed",
    4720: "User Account Created",
    4722: "User Account Enabled",
    4723: "User Account Password Change Attempt",
    4724: "User Account Password Reset Attempt",
    4725: "User Account Disabled",
    4726: "User Account Deleted",
    4732: "Security-Enabled Local Group Member Added",
    4733: "Security-Enabled Local Group Member Removed",
    4738: "User Account Changed",
    4740: "User Account Locked Out",
    4768: "Kerberos TGT Request",
    4769: "Kerberos Service Ticket Request",
    4776: "NTLM Authentication",
    4778: "Session Reconnected",
    4780: "Session Disconnected",
    4946: "Windows Firewall Rule Added",
    4947: "Windows Firewall Rule Modified",
    4948: "Windows Firewall Rule Deleted",
    4950: "Windows Firewall Setting Changed",
    5058: "Key File Operation",
    5059: "Key Migration",
    5061: "Cryptographic Operation",
    5140: "Network Share Accessed",
    5145: "Network Share Permission Checked",
}

SYSTEM_EVENT_IDS = {
    7034: "Service Crashed",
    7035: "Service Start Pending",
    7036: "Service State Change",
    7040: "Service Start Type Changed",
    7045: "Service Installed",
    1001: "Bugcheck (BSOD)",
    1002: "System Recovery",
    1073: "Boot Time",
    1074: "Shutdown",
    6005: "Event Log Service Started",
    6006: "Event Log Service Stopped",
    6008: "Unexpected Shutdown",
    6009: "System Version",
    6013: "System Uptime",
}

SYSMON_EVENT_IDS = {
    1: "Process Creation",
    2: "File Creation Time Changed",
    3: "Network Connection",
    4: "Sysmon Service State Change",
    5: "Process Termination",
    6: "Driver Load",
    7: "Image Load",
    8: "CreateRemoteThread",
    9: "RawAccessRead",
    10: "ProcessAccess",
    11: "FileCreate",
    12: "RegistryEvent",
    13: "RegistryValueSet",
    14: "RegistryKeyRename",
    15: "FileCreateStreamHash",
    16: "SysmonConfigChange",
    17: "PipeEvent",
    18: "PipeCreated",
    19: "WmiEvent",
    20: "WmiEventConsumer",
    21: "WmiEventFilter",
    22: "DnsQuery",
    23: "FileDelete",
    24: "ClipboardChange",
    25: "ProcessTampering",
    26: "FileDeleteDetected",
}

# All recommended event IDs for collection
RECOMMENDED_EVENT_IDS = set(
    list(SECURITY_EVENT_IDS.keys()) +
    list(SYSTEM_EVENT_IDS.keys()) +
    list(SYSMON_EVENT_IDS.keys())
)


def get_event_description(channel: str, event_id: int) -> Optional[str]:
    """Get human-readable description for an event ID."""
    if channel == "Security":
        return SECURITY_EVENT_IDS.get(event_id)
    elif channel == "System":
        return SYSTEM_EVENT_IDS.get(event_id)
    elif "Sysmon" in channel:
        return SYSMON_EVENT_IDS.get(event_id)
    return None
