"""
Suppression Rule model for SentinelWatch Backend.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sentinelwatch_backend.models.base import Base


class SuppressionType(str, enum.Enum):
    """Types of suppression rules."""
    ALERT = "alert"
    RULE = "rule"
    AGENT = "agent"
    GLOBAL = "global"


class SuppressionRule(Base):
    """Suppression rule for alert deduplication and filtering."""

    __tablename__ = "suppression_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Rule type
    rule_type: Mapped[str] = mapped_column(
        Enum(SuppressionType), nullable=False, index=True
    )

    # Target specification
    target_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Suppression condition
    condition: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional severity filter
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Active status
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)

    # Expiry
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Ownership
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)

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

    # Indexes
    __table_args__ = (
        Index("ix_suppression_rules_type_active", "rule_type", "is_active"),
        Index("ix_suppression_rules_target", "target_id", "target_type"),
        Index("ix_suppression_rules_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<SuppressionRule(id={self.id}, name={self.name}, active={self.is_active})>"

    @property
    def is_expired(self) -> bool:
        """Check if suppression has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
