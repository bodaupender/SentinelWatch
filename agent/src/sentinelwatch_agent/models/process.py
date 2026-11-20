"""
Process Telemetry Models for SentinelWatch Agent.
"""

from datetime import datetime, timezone
from typing import Any, Optional, List

from pydantic import BaseModel, Field, ConfigDict

from .base import TelemetryBase


class ProcessHashInfo(BaseModel):
    """Hash information for process executable."""

    model_config = ConfigDict(extra="forbid")

    sha256: Optional[str] = Field(None, description="SHA-256 hash of executable", pattern=r"^[a-fA-F0-9]{64}$")
    md5: Optional[str] = Field(None, description="MD5 hash of executable", pattern=r"^[a-fA-F0-9]{32}$")
    sha1: Optional[str] = Field(None, description="SHA-1 hash of executable", pattern=r"^[a-fA-F0-9]{40}$")
    authentihash: Optional[str] = Field(None, description="Authenticode hash (PE files)")


class ProcessSignatureInfo(BaseModel):
    """Digital signature information for process executable."""

    model_config = ConfigDict(extra="forbid")

    is_signed: bool = Field(False, description="Whether executable has a valid signature")
    signer_name: Optional[str] = Field(None, description="Certificate subject name")
    issuer_name: Optional[str] = Field(None, description="Certificate issuer name")
    timestamp: Optional[datetime] = Field(None, description="Signature timestamp")
    is_trusted: bool = Field(False, description="Whether certificate chain is trusted")
    verification_error: Optional[str] = Field(None, description="Signature verification error if any")


class ProcessTreeNode(BaseModel):
    """Node in process tree for reconstruction."""

    model_config = ConfigDict(extra="forbid")

    pid: int = Field(..., ge=0, description="Process ID")
    ppid: int = Field(..., ge=0, description="Parent process ID")
    name: str = Field(..., min_length=1, max_length=255, description="Process name")
    exe: Optional[str] = Field(None, max_length=4096, description="Executable path")
    cmdline: Optional[str] = Field(None, max_length=32768, description="Command line")
    username: Optional[str] = Field(None, max_length=255, description="Process owner")
    create_time: Optional[datetime] = Field(None, description="Process creation time")
    children: List["ProcessTreeNode"] = Field(default_factory=list, description="Child processes")


ProcessTreeNode.model_rebuild()


class ProcessTelemetry(TelemetryBase):
    """Process telemetry record collected from Windows endpoint."""

    model_config = ConfigDict(extra="forbid")

    # Process identification
    pid: int = Field(..., ge=0, le=4194304, description="Process ID")
    ppid: int = Field(..., ge=0, le=4194304, description="Parent process ID")
    name: str = Field(..., min_length=1, max_length=255, description="Process name")
    exe: Optional[str] = Field(None, max_length=4096, description="Executable path")
    cmdline: Optional[str] = Field(None, max_length=32768, description="Command line (may be redacted)")
    username: Optional[str] = Field(None, max_length=255, description="Process owner")

    # Process timing
    create_time: Optional[datetime] = Field(None, description="Process creation time (UTC) with millisecond precision")
    observed_at: Optional[datetime] = Field(None, description="When the process was last observed by the agent (UTC)")
    terminated_at: Optional[datetime] = Field(None, description="When the process was detected as terminated (UTC)")
    ingested_at: Optional[datetime] = Field(None, description="When the telemetry was ingested by the backend (UTC)")

    # Resource usage
    cpu_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="CPU usage percentage")
    memory_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Memory usage percentage")
    memory_rss_bytes: Optional[int] = Field(None, ge=0, description="Resident Set Size in bytes")
    memory_vms_bytes: Optional[int] = Field(None, ge=0, description="Virtual Memory Size in bytes")
    num_threads: Optional[int] = Field(None, ge=0, description="Number of threads")
    num_handles: Optional[int] = Field(None, ge=0, description="Number of open handles (Windows)")

    # Process status
    status: Optional[str] = Field(None, description="Process status (running, sleeping, zombie, etc.)")
    integrity_level: Optional[str] = Field(None, description="Mandatory integrity level (Windows)")

    # Network connections
    connections: Optional[List[dict]] = Field(None, description="Network connections")

    # Executable hashes
    hashes: Optional[ProcessHashInfo] = Field(None, description="Executable hash information")

    # Digital signature
    signature: Optional[ProcessSignatureInfo] = Field(None, description="Signature information")

    # Parent process info (for tree reconstruction without full tree)
    parent_name: Optional[str] = Field(None, max_length=255, description="Parent process name")
    parent_exe: Optional[str] = Field(None, max_length=4096, description="Parent executable path")

    # Collection metadata
    collection_error: Optional[str] = Field(None, description="Error during collection if any")
    is_complete: bool = Field(True, description="Whether all fields were collected successfully")


# Type alias for process tree
ProcessTree = List[ProcessTreeNode]
