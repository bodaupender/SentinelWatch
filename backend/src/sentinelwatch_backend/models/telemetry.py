"""
Telemetry models for SentinelWatch Backend.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinelwatch_backend.models.base import Base


class ProcessTelemetry(Base):
    """Process telemetry from agents."""
    __tablename__ = "process_telemetry"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Collection metadata
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Process information
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    ppid: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cmdline: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exe: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    create_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    terminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc))

    # Resource usage
    cpu_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    memory_rss_bytes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    num_threads: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    num_handles: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Network connections (JSON array)
    connections: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # File hash
    exe_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # Integrity level
    integrity_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Parent process information (for detection rules)
    parent_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parent_exe: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="process_telemetry")

    # Indexes
    __table_args__ = (
        Index("ix_process_telemetry_agent_collected", "agent_id", "collected_at"),
        Index("ix_process_telemetry_name_collected", "name", "collected_at"),
    )

    def __repr__(self) -> str:
        return f"<ProcessTelemetry(pid={self.pid}, name={self.name}, agent={self.agent_id})>"


class ServiceTelemetry(Base):
    """Windows service telemetry from agents."""
    __tablename__ = "service_telemetry"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # RUNNING, STOPPED, etc.
    start_type: Mapped[str] = mapped_column(String(50), nullable=False)  # AUTO, MANUAL, DISABLED
    pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    binary_path: Mapped[Optional[str]] = mapped_column(String(4096), nullable=True)
    service_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dependencies: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    account: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    exe_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    agent = relationship("Agent", back_populates="service_telemetry")

    __table_args__ = (
        Index("ix_service_telemetry_agent_collected", "agent_id", "collected_at"),
        Index("ix_service_telemetry_name_status", "name", "status"),
    )

    def __repr__(self) -> str:
        return f"<ServiceTelemetry(name={self.name}, status={self.status})>"


class StartupInventory(Base):
    """Startup inventory from agents."""
    __tablename__ = "startup_inventory"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # registry, task, folder, wmi
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    command: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_context: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    exe_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    agent = relationship("Agent", back_populates="startup_inventory")

    __table_args__ = (
        Index("ix_startup_inventory_agent_collected", "agent_id", "collected_at"),
    )

    def __repr__(self) -> str:
        return f"<StartupInventory(source={self.source}, name={self.name})>"


class EventLogEntry(Base):
    """Windows Event Log entries from agents."""
    __tablename__ = "event_log_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    computer: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    raw_xml: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Full XML for important events

    # Extracted fields (for common event IDs)
    extracted: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Original timestamp from event log
    event_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    agent = relationship("Agent", back_populates="event_log_entries")

    __table_args__ = (
        Index("ix_event_log_agent_collected", "agent_id", "collected_at"),
        Index("ix_event_log_source_level", "source", "level"),
    )

    def __repr__(self) -> str:
        return f"<EventLogEntry(event_id={self.event_id}, source={self.source})>"
