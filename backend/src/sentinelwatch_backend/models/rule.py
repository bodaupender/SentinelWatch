"""
Detection Rule model for SentinelWatch Backend.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class RuleType(str, enum.Enum):
    """Rule evaluation type."""

    PROCESS = "process"
    SERVICE = "service"
    STARTUP = "startup"
    EVENTLOG = "eventlog"
    CORRELATION = "correlation"  # Multi-event correlation


class RuleStatus(str, enum.Enum):
    """Rule lifecycle status."""

    DRAFT = "draft"
    STAGING = "staging"  # Testing in staging
    ACTIVE = "active"  # Production
    DISABLED = "disabled"
    DEPRECATED = "deprecated"


class RuleSeverity(str, enum.Enum):
    """Default severity for alerts from this rule."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Rule(Base):
    """Detection rule definition."""

    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Rule identification
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Rule logic
    rule_type: Mapped[RuleType] = mapped_column(Enum(RuleType), nullable=False, index=True)
    condition: Mapped[str] = mapped_column(Text, nullable=False)  # CEL expression or YARA-L-like rule
    condition_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Metadata
    status: Mapped[RuleStatus] = mapped_column(Enum(RuleStatus), default=RuleStatus.DRAFT, nullable=False, index=True)
    severity: Mapped[RuleSeverity] = mapped_column(Enum(RuleSeverity), default=RuleSeverity.MEDIUM, nullable=False)

    # MITRE ATT&CK mapping
    mitre_techniques: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    mitre_tactics: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Tags for categorization
    tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Testing
    test_cases: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # Sample telemetry for testing
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    test_results: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Performance
    evaluation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_evaluation_time_ms: Mapped[float] = mapped_column(default=0.0, nullable=False)
    avg_evaluation_time_ms: Mapped[float] = mapped_column(default=0.0, nullable=False)

    # False positive tracking
    fp_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fp_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    last_fp_reported: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    previous_version_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    promoted_from_staging_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Ownership
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

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

    __table_args__ = (
        Index("ix_rules_status_type", "status", "rule_type"),
        Index("ix_rules_mitre", "mitre_techniques"),
    )

    def __repr__(self) -> str:
        return f"<Rule(id={self.id}, name={self.name}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        return self.status == RuleStatus.ACTIVE

    def record_evaluation(self, duration_ms: float) -> None:
        """Record rule evaluation performance."""
        self.evaluation_count += 1
        self.total_evaluation_time_ms += duration_ms
        self.avg_evaluation_time_ms = self.total_evaluation_time_ms / self.evaluation_count

    def record_false_positive(self) -> None:
        """Record a false positive report."""
        self.fp_count += 1
        if self.evaluation_count > 0:
            self.fp_rate = self.fp_count / self.evaluation_count
        self.last_fp_reported = datetime.now(timezone.utc)
