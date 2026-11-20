"""
Detection Rule model for SentinelWatch Backend.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..models.base import Base


class RuleStatus(str, enum.Enum):
    """Rule lifecycle status."""
    ACTIVE = "active"
    DRAFT = "draft"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class RuleType(str, enum.Enum):
    """Detection rule types."""
    CONDITION = "condition"
    CORRELATION = "correlation"
    THRESHOLD = "threshold"


class RuleSeverity(str, enum.Enum):
    """Rule severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Rule(Base):
    """Custom detection rule."""

    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)  # condition, correlation, threshold
    condition: Mapped[str] = mapped_column(Text, nullable=False)
    condition_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    severity: Mapped[str] = mapped_column(
        Enum(RuleSeverity), default=RuleSeverity.MEDIUM, nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(RuleStatus), default=RuleStatus.DRAFT, nullable=False, index=True
    )

    mitre_techniques: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    mitre_tactics: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    previous_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    promoted_from_staging_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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

    __table_args__ = (
        Index("uq_rules_organization_name", "organization_id", "name", unique=True),
        Index("ix_rules_status_type", "status", "rule_type"),
        Index("ix_rules_mitre", "mitre_techniques"),
    )

    def __repr__(self) -> str:
        return f"<Rule(id={self.id}, name={self.name}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        return self.status == "active"
