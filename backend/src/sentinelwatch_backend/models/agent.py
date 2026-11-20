"""
Agent model for SentinelWatch Backend.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class AgentStatus(str, enum.Enum):
    """Agent connection status."""
    ONLINE = "online"
    OFFLINE = "offline"
    STALE = "stale"  # Missed heartbeats
    UNREGISTERED = "unregistered"  # Pending registration


class Agent(Base):
    """Agent/endpoint registration and metadata."""

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    organization = relationship("Organization")

    # Identity
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    machine_guid: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    os_version: Mapped[str] = mapped_column(String(512), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)

    # Network
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    last_seen_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Certificate (for mTLS)
    cert_fingerprint: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True, index=True)
    cert_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        Enum(AgentStatus), default="unregistered", nullable=False, index=True
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Configuration
    config_version: Mapped[int] = mapped_column(default=0, nullable=False)
    config_applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Metadata
    tags: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Comma-separated
    enrollment_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    enrolled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Identity validation fields
    identity_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # SHA256 of fingerprint
    last_fingerprint: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # Last known fingerprint
    re_enrollment_count: Mapped[int] = mapped_column(default=0, nullable=False)
    credential_version: Mapped[int] = mapped_column(default=0, nullable=False)

    # Health
    health_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    health_alerts: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    process_telemetry = relationship("ProcessTelemetry", back_populates="agent", lazy="dynamic")
    service_telemetry = relationship("ServiceTelemetry", back_populates="agent", lazy="dynamic")
    startup_inventory = relationship("StartupInventory", back_populates="agent", lazy="dynamic")
    event_log_entries = relationship("EventLogEntry", back_populates="agent", lazy="dynamic")
    alerts = relationship("Alert", back_populates="agent", lazy="dynamic")
    credential = relationship(
        "AgentCredential", back_populates="agent", uselist=False,
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("ix_agents_status_last_seen", "status", "last_seen"),
        Index("ix_agents_hostname_status", "hostname", "status"),
    )

    def __repr__(self) -> str:
        return f"<Agent(id={self.id}, hostname={self.hostname}, status={self.status})>"

    @property
    def is_online(self) -> bool:
        """Check if agent is considered online."""
        if self.status != "online":
            return False
        if not self.last_heartbeat:
            return False
        # Consider stale if no heartbeat for 3 intervals (3 minutes default)
        threshold = datetime.now(timezone.utc) - self.last_heartbeat
        return threshold.total_seconds() < 180

    @property
    def cert_expiring_soon(self, days: int = 30) -> bool:
        """Check if certificate expires within specified days."""
        if not self.cert_expires_at:
            return False
        threshold = datetime.now(timezone.utc)
        return (self.cert_expires_at - threshold).days <= days
