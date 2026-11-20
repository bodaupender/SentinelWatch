"""
Startup Inventory Telemetry Models for SentinelWatch Agent.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class StartupSource(str, Enum):
    """Source of startup entry."""

    REGISTRY_RUN = "registry_run"
    REGISTRY_RUN_ONCE = "registry_runonce"
    REGISTRY_WINLOGON = "registry_winlogon"
    STARTUP_FOLDER_USER = "startup_folder_user"
    STARTUP_FOLDER_COMMON = "startup_folder_common"
    SCHEDULED_TASK = "scheduled_task"
    SERVICE = "service"
    WMI_SUBSCRIPTION = "wmi_subscription"
    BROWSER_HELPER = "browser_helper"
    SHELL_EXTENSION = "shell_extension"
    DRIVER = "driver"
    IMAGE_HIJACK = "image_hijack"
    KNOWN_DLL = "known_dll"
    APPINIT_DLL = "appinit_dll"
    OTHER = "other"


class StartupTelemetry(BaseModel):
    """Startup inventory telemetry record."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Unique agent identifier")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = Field(..., description="Monotonically increasing sequence number")

    # Entry identification
    source: StartupSource = Field(..., description="Source of startup entry")
    source_key: Optional[str] = Field(None, max_length=1024, description="Registry key or task path")
    name: str = Field(..., min_length=1, max_length=255, description="Entry name")
    command: Optional[str] = Field(None, max_length=4096, description="Command to execute")
    arguments: Optional[str] = Field(None, max_length=4096, description="Command arguments")

    # Context
    user_context: Optional[str] = Field(None, max_length=255, description="User context (SID or username)")
    user_sid: Optional[str] = Field(None, description="User SID if available")
    run_as_admin: bool = Field(False, description="Whether runs with elevated privileges")

    # File information
    executable_path: Optional[str] = Field(None, max_length=4096, description="Path to executable")
    working_directory: Optional[str] = Field(None, max_length=4096, description="Working directory")

    # Hash information
    exe_sha256: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{64}$", description="SHA-256 of executable")
    exe_md5: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{32}$", description="MD5 of executable")

    # Signature information
    is_signed: bool = Field(False, description="Whether executable is digitally signed")
    signer_name: Optional[str] = Field(None, description="Certificate signer name")

    # Status
    enabled: bool = Field(True, description="Whether entry is enabled")
    last_observed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When last observed")

    # Registry-specific
    registry_hive: Optional[str] = Field(None, description="Registry hive (HKLM, HKCU, etc.)")
    registry_key_path: Optional[str] = Field(None, max_length=1024, description="Full registry key path")
    registry_value_type: Optional[str] = Field(None, description="Registry value type (REG_SZ, REG_EXPAND_SZ)")

    # Scheduled task specific
    task_triggers: Optional[str] = Field(None, description="Task trigger description")
    task_actions: Optional[str] = Field(None, description="Task action description")
    task_conditions: Optional[str] = Field(None, description="Task conditions")
    task_settings: Optional[str] = Field(None, description="Task settings")

    # WMI subscription specific
    wmi_filter: Optional[str] = Field(None, description="WMI event filter query")
    wmi_consumer: Optional[str] = Field(None, description="WMI consumer (command to run)")

    # Collection metadata
    collection_error: Optional[str] = Field(None, description="Error during collection if any")
    is_complete: bool = Field(True, description="Whether all fields were collected successfully")


# Registry paths to monitor
REGISTRY_RUN_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnceEx",
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Userinit",
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon\Shell",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnce",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\RunOnceEx",
]

REGISTRY_POLICIES_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run",
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System\Shell",
]

REGISTRY_WINLOGON_KEYS = [
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon",
]
