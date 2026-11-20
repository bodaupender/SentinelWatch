"""
User model for SentinelWatch Backend.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


class UserRole(str, enum.Enum):
    """User roles for RBAC."""

    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"
    AGENT = "agent"  # For agent API access


class UserStatus(str, enum.Enum):
    """User account status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
    PENDING = "pending"  # Pending MFA setup or email verification


class User(Base):
    """User account for dashboard access."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Identity
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Authentication
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # MFA
    mfa_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # TOTP secret
    mfa_backup_codes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Role and permissions
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER, nullable=False, index=True)
    permissions: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # Additional granular permissions

    # Status
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.PENDING, nullable=False, index=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)

    # Session management
    refresh_tokens: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)  # Active refresh token hashes

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

    organization_memberships = relationship(
        "OrganizationMembership", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_status_role", "status", "role"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_locked(self) -> bool:
        if self.locked_until:
            return datetime.now(timezone.utc) < self.locked_until
        return False

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        if self.role == UserRole.ADMIN:
            return True
        if self.permissions and permission in self.permissions:
            return True
        # Default role permissions
        role_permissions = {
            UserRole.ANALYST: [
                "alerts.read", "alerts.triage", "alerts.resolve",
                "agents.read", "processes.read", "services.read",
                "rules.read", "rules.test",
                "audit.read",
            ],
            UserRole.VIEWER: [
                "alerts.read", "agents.read", "processes.read",
                "services.read", "rules.read", "audit.read",
            ],
        }
        return permission in role_permissions.get(self.role, [])


class ApiKey(Base):
    """API keys for programmatic access."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)  # First 8 chars for identification

    # Scopes
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Ownership
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Status
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    user = relationship("User")

    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, name={self.name}, prefix={self.key_prefix})>"
