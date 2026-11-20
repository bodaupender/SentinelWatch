"""
Service Telemetry Models for SentinelWatch Agent.
"""

from datetime import datetime, timezone
from typing import Any, Optional, List

from pydantic import BaseModel, Field, ConfigDict


class ServiceConfigInfo(BaseModel):
    """Service configuration details for security auditing."""

    model_config = ConfigDict(extra="forbid")

    # Path analysis
    binary_path: Optional[str] = Field(None, max_length=4096, description="Service binary path")
    is_path_quoted: bool = Field(False, description="Whether binary path is properly quoted")
    has_spaces_in_path: bool = Field(False, description="Whether path contains spaces (requires quotes)")
    path_exists: bool = Field(False, description="Whether binary path exists on filesystem")

    # Permissions analysis
    binary_writable_by_user: bool = Field(False, description="Binary writable by non-admin users")
    directory_writable_by_user: bool = Field(False, description="Parent directory writable by non-admin users")
    binary_owner: Optional[str] = Field(None, description="Binary file owner")
    directory_owner: Optional[str] = Field(None, description="Parent directory owner")

    # Security findings
    is_unquoted_with_spaces: bool = Field(False, description="Unquoted path containing spaces")
    is_in_writable_location: bool = Field(False, description="Binary in user-writable directory")
    has_suspicious_name: bool = Field(False, description="Service name appears suspicious")
    has_suspicious_binary_name: bool = Field(False, description="Binary name appears suspicious (e.g., svchost.exe in wrong location)")


class ServiceSignatureInfo(BaseModel):
    """Digital signature information for service executable."""

    model_config = ConfigDict(extra="forbid")

    is_signed: bool = Field(False, description="Whether executable has a valid signature")
    signer_name: Optional[str] = Field(None, description="Certificate subject name")
    issuer_name: Optional[str] = Field(None, description="Certificate issuer name")
    timestamp: Optional[datetime] = Field(None, description="Signature timestamp")
    is_trusted: bool = Field(False, description="Whether certificate chain is trusted")
    verification_error: Optional[str] = Field(None, description="Signature verification error if any")


class ServiceHashInfo(BaseModel):
    """Hash information for service executable."""

    model_config = ConfigDict(extra="forbid")

    sha256: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{64}$")
    md5: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{32}$")
    sha1: Optional[str] = Field(None, pattern=r"^[a-fA-F0-9]{40}$")


class ServiceTelemetry(BaseModel):
    """Windows service telemetry record."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Unique agent identifier")
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = Field(..., description="Monotonically increasing sequence number")

    # Service identification
    name: str = Field(..., min_length=1, max_length=255, description="Service name")
    display_name: Optional[str] = Field(None, max_length=255, description="Service display name")
    description: Optional[str] = Field(None, max_length=1024, description="Service description")

    # Service state
    status: str = Field(..., description="Service status: running, stopped, paused, start_pending, stop_pending, continue_pending, pause_pending")
    start_type: str = Field(..., description="Startup type: auto, manual, disabled, delayed_auto")
    service_type: str = Field(..., description="Service type: own_process, share_process, kernel_driver, file_system_driver, interactive_process")

    # Service account and binary
    service_account: Optional[str] = Field(None, description="Service logon account (LocalSystem, NetworkService, LocalService, or user)")
    binary_path: Optional[str] = Field(None, max_length=4096, description="Full path to service executable")

    # Service PID
    pid: Optional[int] = Field(None, ge=0, description="Process ID if service is running")

    # Dependencies
    dependencies: List[str] = Field(default_factory=list, description="Service dependencies")

    # Load order group
    load_order_group: Optional[str] = Field(None, description="Load order group")

    # Error control
    error_control: Optional[str] = Field(None, description="Error control: normal, severe, critical, ignore")

    # Service executable hashes
    hashes: Optional[ServiceHashInfo] = Field(None, description="Executable hash information")

    # Digital signature
    signature: Optional[ServiceSignatureInfo] = Field(None, description="Signature information")

    # Security audit findings
    config_audit: Optional[ServiceConfigInfo] = Field(None, description="Security configuration audit results")

    # Collection metadata
    collection_error: Optional[str] = Field(None, description="Error during collection if any")
    is_complete: bool = Field(True, description="Whether all fields were collected successfully")


# Service status constants
class ServiceStatus:
    STOPPED = "stopped"
    START_PENDING = "start_pending"
    STOP_PENDING = "stop_pending"
    RUNNING = "running"
    CONTINUE_PENDING = "continue_pending"
    PAUSE_PENDING = "pause_pending"
    PAUSED = "paused"

    @classmethod
    def from_windows_state(cls, state: int) -> str:
        """Convert Windows service state constant to string."""
        states = {
            1: cls.STOPPED,
            2: cls.START_PENDING,
            3: cls.STOP_PENDING,
            4: cls.RUNNING,
            5: cls.CONTINUE_PENDING,
            6: cls.PAUSE_PENDING,
            7: cls.PAUSED,
        }
        return states.get(state, "unknown")


class ServiceStartType:
    BOOT_START = "boot"
    SYSTEM_START = "system"
    AUTO_START = "auto"
    DELAYED_AUTO_START = "delayed_auto"
    DEMAND_START = "manual"
    DISABLED = "disabled"

    @classmethod
    def from_windows_start_type(cls, start_type: int) -> str:
        """Convert Windows start type constant to string."""
        types = {
            0: cls.BOOT_START,
            1: cls.SYSTEM_START,
            2: cls.AUTO_START,
            3: cls.DEMAND_START,
            4: cls.DISABLED,
        }
        return types.get(start_type, "unknown")


class ServiceType:
    KERNEL_DRIVER = "kernel_driver"
    FILE_SYSTEM_DRIVER = "file_system_driver"
    WIN32_OWN_PROCESS = "own_process"
    WIN32_SHARE_PROCESS = "share_process"
    INTERACTIVE_PROCESS = "interactive_process"

    @classmethod
    def from_windows_type(cls, service_type: int) -> str:
        """Convert Windows service type constant to string."""
        types = {
            1: cls.KERNEL_DRIVER,
            2: cls.FILE_SYSTEM_DRIVER,
            16: cls.WIN32_OWN_PROCESS,
            32: cls.WIN32_SHARE_PROCESS,
            256: cls.INTERACTIVE_PROCESS,
        }
        # Handle combined types
        result = []
        for flag, name in types.items():
            if service_type & flag:
                result.append(name)
        return ",".join(result) if result else "unknown"
