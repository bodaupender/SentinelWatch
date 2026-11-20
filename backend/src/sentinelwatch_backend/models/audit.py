"""
Audit Log model for SentinelWatch Backend.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditActorType(str, enum.Enum):
    """Type of actor performing the action."""

    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class AuditResult(str, enum.Enum):
    """Result of the audited action."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"


class AuditLog(Base):
    """Immutable audit log entry."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Actor information
    actor_type: Mapped[AuditActorType] = mapped_column(Enum(AuditActorType), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Username, agent hostname, etc.

    # Action
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Details (structured, no PII)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    # Result
    result: Mapped[AuditResult] = mapped_column(Enum(AuditResult), default=AuditResult.SUCCESS, nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamp (immutable)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    # No updated_at - audit logs are immutable
    # No deleted_at - audit logs are never deleted (WORM)

    __table_args__ = (
        Index("ix_audit_log_timestamp_actor", "timestamp", "actor_id"),
        Index("ix_audit_log_action_result", "action", "result"),
        Index("ix_audit_log_resource", "resource_type", "resource_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action}, actor={self.actor_type}:{self.actor_id})>"

    @classmethod
    def create(
        cls,
        action: str,
        organization_id: str,
        actor_type: AuditActorType,
        actor_id: str,
        actor_name: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        result: AuditResult = AuditResult.SUCCESS,
        error_message: Optional[str] = None,
    ) -> "AuditLog":
        """Create a new audit log entry."""
        return cls(
            action=action,
            organization_id=organization_id,
            actor_type=actor_type,
            actor_id=actor_id,
            actor_name=actor_name,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            result=result,
            error_message=error_message,
        )
