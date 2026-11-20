"""Enrollment Token model for SentinelWatch Backend.

Provides secure, time-limited enrollment tokens for agent registration.
"""

import enum
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EnrollmentTokenStatus(str, enum.Enum):
    """Enrollment token status."""
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


class EnrollmentToken(Base):
    """Enrollment token for secure agent registration."""

    __tablename__ = "enrollment_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization = relationship("Organization")

    # Token (hashed for storage)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(8), nullable=False)  # First 8 chars for identification

    # Metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # Human-readable name
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(
        Enum(EnrollmentTokenStatus), default=EnrollmentTokenStatus.ACTIVE, nullable=False, index=True
    )

    # Expiration
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Usage tracking
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_agent_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    used_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_uses: Mapped[int] = mapped_column(default=1, nullable=False)

    # Revocation
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    revoked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Ownership
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Admin user who created

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
        Index("ix_enrollment_tokens_status_expires", "status", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<EnrollmentToken(id={self.id}, prefix={self.token_prefix}, status={self.status})>"

    @classmethod
    def generate_token(cls, length: int = 32) -> str:
        """Generate a cryptographically secure enrollment token."""
        return secrets.token_urlsafe(length)

    @classmethod
    def hash_token(cls, token: str) -> str:
        """Hash a token for storage."""
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()

    @classmethod
    def get_token_prefix(cls, token: str) -> str:
        """Get the first 8 characters of a token for identification."""
        return token[:8]

    def verify_token(self, token: str) -> bool:
        """Verify a plain token against stored hash."""
        return secrets.compare_digest(self.token_hash, self.hash_token(token))

    def is_valid(self) -> bool:
        """Check if token is valid for use."""
        if self.status != EnrollmentTokenStatus.ACTIVE:
            return False
        if self.expires_at:
            # Normalize expires_at to UTC for comparison.
            # Handles both naive datetimes (from SQLite) and timezone-aware datetimes.
            expires_at = self.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            else:
                # Already timezone-aware: convert to UTC if not already
                expires_at = expires_at.astimezone(timezone.utc)
            if datetime.now(timezone.utc) >= expires_at:
                return False
        if self.used_count >= self.max_uses:
            return False
        return True

    def mark_used(self, agent_id: str) -> None:
        """Mark token as used."""
        self.used_count += 1
        self.used_at = datetime.now(timezone.utc)
        self.used_by_agent_id = agent_id
        if self.used_count >= self.max_uses:
            self.status = EnrollmentTokenStatus.USED

    def revoke(self, revoked_by: str, reason: str) -> None:
        """Revoke the token."""
        self.status = EnrollmentTokenStatus.REVOKED
        self.revoked_at = datetime.now(timezone.utc)
        self.revoked_by = revoked_by
        self.revoked_reason = reason
