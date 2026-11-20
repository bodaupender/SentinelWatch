"""Enrollment Token API endpoints for SentinelWatch Backend.

Manages secure enrollment tokens for agent registration.
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, or_, select

from ...database import get_db
from ...models import EnrollmentToken, Organization, User
from ...config import get_config
from ...auth import decode_token
from ..deps import get_current_user, get_current_organization_admin
from ...logging import get_logger

router = APIRouter(prefix="/enrollment-tokens", tags=["enrollment-tokens"])

logger = get_logger(__name__)
DEFAULT_ENROLLMENT_TTL_DAYS = 7
MAX_ENROLLMENT_TTL_DAYS = 30


# Request/Response models
class EnrollmentTokenCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name for the token")
    description: Optional[str] = Field(None, max_length=1000, description="Optional description")
    expires_in_days: Optional[int] = Field(
        None, ge=1, le=MAX_ENROLLMENT_TTL_DAYS,
        description=f"Token expiration in days (maximum {MAX_ENROLLMENT_TTL_DAYS})",
    )
    max_uses: int = Field(1, ge=1, le=1000, description="Maximum number of uses")


class EnrollmentTokenUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    expires_at: Optional[datetime] = None
    max_uses: Optional[int] = Field(None, ge=1, le=1000)

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: Optional[datetime]) -> Optional[datetime]:
        """Prevent edited tokens from being made permanent or long-lived."""
        if value is None:
            return value
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if normalized <= now:
            raise ValueError("expires_at must be in the future")
        if normalized > now + timedelta(days=MAX_ENROLLMENT_TTL_DAYS):
            raise ValueError(f"expires_at cannot be more than {MAX_ENROLLMENT_TTL_DAYS} days away")
        return normalized


class EnrollmentTokenResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    token_prefix: str
    status: str
    expires_at: Optional[datetime]
    used_count: int
    max_uses: int
    used_at: Optional[datetime]
    used_by_agent_id: Optional[str]
    revoked_at: Optional[datetime]
    revoked_by: Optional[str]
    revoked_reason: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EnrollmentTokenCreateResponse(BaseModel):
    id: str
    token: str  # Full token (only returned once on creation)
    token_prefix: str
    message: str = "Enrollment token created. Store the full token securely - it will not be shown again."


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Resolve the signed-in user; tenant administrator checks are scoped per organization."""
    return current_user


@router.post("", response_model=EnrollmentTokenCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_enrollment_token(
    token_data: EnrollmentTokenCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Create a new enrollment token."""
    config = get_config()

    # Generate token
    token = EnrollmentToken.generate_token(32)
    token_hash = EnrollmentToken.hash_token(token)
    token_prefix = EnrollmentToken.get_token_prefix(token)

    # Calculate expiration
    # Enrollment tokens are short-lived by default. Administrators can choose a
    # longer explicit duration, but omission never creates a permanent token.
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=token_data.expires_in_days or DEFAULT_ENROLLMENT_TTL_DAYS
    )

    # Create enrollment token record
    enrollment_token = EnrollmentToken(
        token_hash=token_hash,
        token_prefix=token_prefix,
        organization_id=organization.id,
        name=token_data.name,
        description=token_data.description,
        expires_at=expires_at,
        max_uses=token_data.max_uses,
        created_by=current_user.username,
    )

    db.add(enrollment_token)
    await db.commit()
    await db.refresh(enrollment_token)

    logger.info(
        "enrollment_token_created",
        token_id=enrollment_token.id,
        token_prefix=enrollment_token.token_prefix,
        name=enrollment_token.name,
        created_by=current_user.username,
    )

    return EnrollmentTokenCreateResponse(
        id=enrollment_token.id,
        token=token,
        token_prefix=enrollment_token.token_prefix,
    )


@router.get("", response_model=List[EnrollmentTokenResponse])
async def list_enrollment_tokens(
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """List enrollment tokens with filtering and pagination."""
    query = select(EnrollmentToken).where(EnrollmentToken.organization_id == organization.id)

    if status:
        query = query.filter(EnrollmentToken.status == status)
    if search:
        query = query.filter(EnrollmentToken.name.ilike(f"%{search}%"))

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0

    query = query.order_by(desc(EnrollmentToken.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    tokens = result.scalars().all()

    return [
        EnrollmentTokenResponse(
            id=t.id,
            name=t.name,
            description=t.description,
            token_prefix=t.token_prefix,
            status=t.status,
            expires_at=t.expires_at,
            used_count=t.used_count,
            max_uses=t.max_uses,
            used_at=t.used_at,
            used_by_agent_id=t.used_by_agent_id,
            revoked_at=t.revoked_at,
            revoked_by=t.revoked_by,
            revoked_reason=t.revoked_reason,
            created_by=t.created_by,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in tokens
    ]


@router.get("/{token_id}", response_model=EnrollmentTokenResponse)
async def get_enrollment_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Get enrollment token details."""
    result = await db.execute(select(EnrollmentToken).where(
        EnrollmentToken.id == token_id,
        EnrollmentToken.organization_id == organization.id,
    ))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment token not found"
        )

    return EnrollmentTokenResponse(
        id=token.id,
        name=token.name,
        description=token.description,
        token_prefix=token.token_prefix,
        status=token.status,
        expires_at=token.expires_at,
        used_count=token.used_count,
        max_uses=token.max_uses,
        used_at=token.used_at,
        used_by_agent_id=token.used_by_agent_id,
        revoked_at=token.revoked_at,
        revoked_by=token.revoked_by,
        revoked_reason=token.revoked_reason,
        created_by=token.created_by,
        created_at=token.created_at,
        updated_at=token.updated_at,
    )


@router.patch("/{token_id}", response_model=EnrollmentTokenResponse)
async def update_enrollment_token(
    token_id: str,
    update_data: EnrollmentTokenUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Update enrollment token."""
    result = await db.execute(select(EnrollmentToken).where(
        EnrollmentToken.id == token_id,
        EnrollmentToken.organization_id == organization.id,
    ))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment token not found"
        )

    # Only allow updates for active tokens
    if token.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot update token with status '{token.status}'"
        )

    if update_data.name is not None:
        token.name = update_data.name
    if update_data.description is not None:
        token.description = update_data.description
    if update_data.expires_at is not None:
        token.expires_at = update_data.expires_at
    if update_data.max_uses is not None:
        token.max_uses = update_data.max_uses

    token.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(token)

    logger.info("enrollment_token_updated", token_id=token.id, updated_by=current_user.username)

    return EnrollmentTokenResponse(
        id=token.id,
        name=token.name,
        description=token.description,
        token_prefix=token.token_prefix,
        status=token.status,
        expires_at=token.expires_at,
        used_count=token.used_count,
        max_uses=token.max_uses,
        used_at=token.used_at,
        used_by_agent_id=token.used_by_agent_id,
        revoked_at=token.revoked_at,
        revoked_by=token.revoked_by,
        revoked_reason=token.revoked_reason,
        created_by=token.created_by,
        created_at=token.created_at,
        updated_at=token.updated_at,
    )


@router.post("/{token_id}/revoke", response_model=dict)
async def revoke_enrollment_token(
    token_id: str,
    revoke_data: dict,  # {reason: str}
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Revoke an enrollment token."""
    result = await db.execute(select(EnrollmentToken).where(
        EnrollmentToken.id == token_id,
        EnrollmentToken.organization_id == organization.id,
    ))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment token not found"
        )

    if token.status not in ("active", "expired"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot revoke token with status '{token.status}'"
        )

    reason = revoke_data.get("reason", "Revoked by admin")
    token.revoke(current_user.username, reason)
    await db.commit()

    logger.info("enrollment_token_revoked", token_id=token.id, revoked_by=current_user.username, reason=reason)

    return {"message": "Enrollment token revoked", "token_id": token_id}


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enrollment_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Delete an enrollment token (soft delete)."""
    result = await db.execute(select(EnrollmentToken).where(
        EnrollmentToken.id == token_id,
        EnrollmentToken.organization_id == organization.id,
    ))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment token not found"
        )

    token.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("enrollment_token_deleted", token_id=token_id, deleted_by=current_user.username)


@router.get("/{token_id}/validate", response_model=dict)
async def validate_enrollment_token(
    token_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Validate an enrollment token (used by agent during registration)."""
    # This endpoint doesn't require auth - it's called by agents with the token
    # We identify the token by looking up the prefix
    # For security, we should not enumerate tokens; agents provide the full token

    # This endpoint is intentionally not implemented as a separate API call
    # Token validation happens during registration via the enrollment_token field
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Use the registration endpoint with the enrollment token"
    )
