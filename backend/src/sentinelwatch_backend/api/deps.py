"""
API Dependencies for SentinelWatch Backend.

Provides common dependencies for FastAPI endpoints.
"""

from typing import Optional, Generator
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..config import get_config
from sentinelwatch_backend.database import get_db
from sentinelwatch_backend.models import Organization, OrganizationMembership, OrganizationRole, OrganizationStatus, User
from sentinelwatch_backend.auth import decode_token, TokenData

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db = Depends(get_db),
) -> "User":
    """Get current authenticated user from JWT token."""
    from sentinelwatch_backend.models import User
    from sentinelwatch_backend.auth import decode_token
    from sentinelwatch_backend.config import get_config

    config = get_config()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    # Reject access tokens issued before a password change so that clearing
    # refresh tokens also invalidates already-issued access tokens.
    if user.password_changed_at and payload.get("iat") is not None:
        changed_at = user.password_changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        try:
            issued_at = datetime.fromtimestamp(float(payload["iat"]), tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            raise credentials_exception
        if issued_at < changed_at:
            raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    return user


async def get_current_organization(
    selected_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
    current_user: "User" = Depends(get_current_user),
    db = Depends(get_db),
) -> Organization:
    """Resolve the active tenant from a verified membership, never from a bare client ID."""
    query = (
        select(Organization)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(
            OrganizationMembership.user_id == current_user.id,
            Organization.status == OrganizationStatus.ACTIVE,
        )
    )
    if selected_organization_id:
        query = query.where(Organization.id == selected_organization_id)

    result = await db.execute(query.limit(2))
    organizations = result.scalars().all()
    if not organizations:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active organization membership for this request",
        )
    if len(organizations) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select an organization using X-Organization-ID",
        )
    return organizations[0]


async def get_current_organization_admin(
    organization: Organization = Depends(get_current_organization),
    current_user: "User" = Depends(get_current_user),
    db = Depends(get_db),
) -> Organization:
    """Require an owner/admin membership in the selected tenant."""
    result = await db.execute(
        select(OrganizationMembership.id).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.role.in_([OrganizationRole.OWNER, OrganizationRole.ADMIN]),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization administrator access required",
        )
    return organization


async def get_current_analyst(
    current_user: "User" = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
    db = Depends(get_db),
) -> "User":
    """Require analyst-level membership in the selected organization."""
    result = await db.execute(
        select(OrganizationMembership.role).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == current_user.id,
        )
    )
    role = result.scalar_one_or_none()
    if role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN, OrganizationRole.ANALYST}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization analyst access required")
    return current_user


async def get_current_admin(
    current_user: "User" = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
    db = Depends(get_db),
) -> "User":
    """Require owner/admin membership in the selected organization."""
    result = await db.execute(
        select(OrganizationMembership.role).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == current_user.id,
        )
    )
    role = result.scalar_one_or_none()
    if role not in {OrganizationRole.OWNER, OrganizationRole.ADMIN}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization administrator access required")
    return current_user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional["User"]:
    """Get current user if token is provided, otherwise return None."""
    if not token:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None
