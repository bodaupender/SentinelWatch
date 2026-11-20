"""
Authentication API endpoints for SentinelWatch Backend.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Form, Cookie
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from ...config import get_config
from ...database import get_db
from ...models import User, Role
from ...models.organization import Organization, OrganizationMembership, OrganizationRole
from ...models.user import UserRole, UserStatus
from ...logging import get_logger
from ...auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    TokenData,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# Token models
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class TokenRefresh(BaseModel):
    refresh_token: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    password: str
    role_id: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    mfa_enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SelfProfileUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(default=None, max_length=255)


class CodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


def _resolve_refresh_token(body_token: Optional[str], cookie_token: Optional[str]) -> str:
    """Accept legacy body tokens or the HttpOnly refresh cookie."""
    token = body_token or cookie_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return token


def _valid_totp(secret: str, code: str) -> bool:
    if not code.isdigit() or len(code) != 6:
        return False
    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    counter = int(time.time()) // 30
    for offset in (-1, 0, 1):
        digest = hmac.new(key, struct.pack(">Q", counter + offset), hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        value = (struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if hmac.compare_digest(f"{value:06d}", code):
            return True
    return False


class UserRegistration(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    full_name: Optional[str] = None
    password: str = Field(min_length=12, max_length=128)

# Re-export consolidated dependencies so existing imports continue to work
from ...api.deps import get_current_user, get_current_analyst, get_current_admin, get_current_organization

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserRegistration,
    db: AsyncSession = Depends(get_db),
):
    """Create a local development account with analyst access."""
    if not get_config().server.debug:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-registration is disabled",
        )

    username = user_data.username.strip()
    email = str(user_data.email).strip().lower()

    result = await db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    result = await db.execute(
        select(User).where(func.lower(User.email) == email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        username=username,
        email=email,
        full_name=user_data.full_name.strip() if user_data.full_name else None,
        password_hash=hash_password(user_data.password),
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )
    slug_base = "".join(character.lower() if character.isalnum() else "-" for character in username)
    slug_base = "-".join(part for part in slug_base.split("-") if part)[:80] or "workspace"
    organization = Organization(
        name=f"{(user_data.full_name or username).strip()}'s Organization",
        slug=f"{slug_base}-{secrets.token_hex(4)}",
    )
    membership = OrganizationMembership(
        user=user,
        organization=organization,
        role=OrganizationRole.OWNER,
    )
    db.add_all([user, organization, membership])
    await db.commit()
    await db.refresh(user)
    logger.info("user_registered", user_id=user.id, role="analyst")
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
    )

@router.post("/login", response_model=Token)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    mfa_code: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return access/refresh tokens."""
    config = get_config()

    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()

    if not user:
        logger.warning("login_failed_user_not_found", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning("login_failed_user_inactive", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    if user.is_locked:
        logger.warning("login_failed_user_locked", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account locked due to failed login attempts"
        )

    if not verify_password(form_data.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        await db.commit()

        logger.warning("login_failed_invalid_password", username=form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reset failed attempts on successful login
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login = datetime.now(timezone.utc)
    user.last_login_ip = "127.0.0.1"  # Would get from request in production
    await db.commit()

    # Check MFA if enabled
    if user.mfa_enabled:
        if not mfa_code or not user.mfa_secret or not _valid_totp(user.mfa_secret, mfa_code):
            raise HTTPException(status_code=401, detail="A valid authenticator code is required", headers={"WWW-Authenticate": "Bearer"})

    # Create tokens
    access_token = create_access_token(
        data={"sub": user.id, "role": user.role},
        expires_delta=timedelta(minutes=config.auth.access_token_expire_minutes)
    )
    refresh_token = create_refresh_token(
        data={"sub": user.id},
        expires_delta=timedelta(days=config.auth.refresh_token_expire_days)
    )

    # Store refresh token for revocation/rotation
    if user.refresh_tokens is None:
        user.refresh_tokens = []
    user.refresh_tokens.append(refresh_token)
    await db.commit()

    logger.info("login_success", user_id=user.id, username=user.username)

    # Set refresh token in HttpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=config.tls.enabled,
        samesite="strict",
        max_age=config.auth.refresh_token_expire_days * 24 * 60 * 60,
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=config.auth.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    response: Response,
    token_data: Optional[TokenRefresh] = None,
    refresh_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token with rotation and revocation."""
    config = get_config()
    raw_refresh_token = _resolve_refresh_token(
        token_data.refresh_token if token_data else None,
        refresh_cookie,
    )

    try:
        payload = decode_token(raw_refresh_token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    # Verify the refresh token is in user's active tokens (revocation check)
    refresh_tokens = user.refresh_tokens or []
    if raw_refresh_token not in refresh_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or invalid"
        )

    # Create new tokens
    access_token = create_access_token(
        data={"sub": user.id, "role": user.role},
        expires_delta=timedelta(minutes=config.auth.access_token_expire_minutes)
    )
    new_refresh_token = create_refresh_token(
        data={"sub": user.id},
        expires_delta=timedelta(days=config.auth.refresh_token_expire_days)
    )

    # Revoke old token, add new one (rotation)
    updated_tokens = [t for t in refresh_tokens if t != raw_refresh_token]
    updated_tokens.append(new_refresh_token)
    user.refresh_tokens = updated_tokens
    await db.commit()

    # Set new refresh token in cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=config.tls.enabled,
        samesite="strict",
        max_age=config.auth.refresh_token_expire_days * 24 * 60 * 60,
    )

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=config.auth.access_token_expire_minutes * 60,
    )


@router.post("/logout")
async def logout(
    response: Response,
    token_data: Optional[TokenRefresh] = None,
    refresh_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout current user."""
    config = get_config()
    raw_refresh_token = token_data.refresh_token if token_data else refresh_cookie
    if raw_refresh_token:
        current_user.refresh_tokens = [
            token for token in (current_user.refresh_tokens or [])
            if token != raw_refresh_token
        ]
        await db.commit()
    # Clear refresh token cookie
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=config.tls.enabled,
        samesite="strict",
    )

    logger.info("logout_success", user_id=current_user.id)

    return {"message": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        mfa_enabled=current_user.mfa_enabled,
        created_at=current_user.created_at,
    )


@router.patch("/me", response_model=UserResponse)
async def update_current_user_profile(
    update: SelfProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the signed-in user's editable profile fields."""
    changes = update.model_dump(exclude_unset=True)
    if "email" in changes:
        duplicate = await db.execute(select(User).where(
            User.email == changes["email"], User.id != current_user.id
        ))
        if duplicate.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Email address is already in use")
        current_user.email = changes["email"]
    if "full_name" in changes:
        current_user.full_name = changes["full_name"]
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Create a new user (admin only)."""
    # Check if username or email exists
    result = await db.execute(select(User).where(User.username == user_data.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    result = await db.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists"
        )

    role = UserRole.VIEWER
    if user_data.role_id:
        role_result = await db.execute(select(Role).where(Role.id == user_data.role_id, Role.is_active.is_(True)))
        role_record = role_result.scalar_one_or_none()
        if not role_record or role_record.name.lower() not in {"admin", "analyst", "viewer"}:
            raise HTTPException(status_code=400, detail="Invalid user role")
        role = UserRole(role_record.name.lower())

    # Hash password
    password_hash = hash_password(user_data.password)

    # Create user
    user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        password_hash=password_hash,
        role=role,
        status=UserStatus.ACTIVE,
    )
    membership_role = {
        UserRole.ADMIN: OrganizationRole.ADMIN,
        UserRole.ANALYST: OrganizationRole.ANALYST,
        UserRole.VIEWER: OrganizationRole.VIEWER,
    }[role]
    db.add_all([
        user,
        OrganizationMembership(user=user, organization=organization, role=membership_role),
    ])
    await db.commit()
    await db.refresh(user)

    logger.info("user_created", user_id=user.id, username=user.username, created_by=current_user.id)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """List members of the selected organization."""
    result = await db.execute(
        select(User).join(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization.id
        ).order_by(User.username).offset(skip).limit(limit)
    )
    users = result.scalars().all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            mfa_enabled=u.mfa_enabled,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Get user by ID (admin only)."""
    result = await db.execute(
        select(User).join(OrganizationMembership).where(
            User.id == user_id, OrganizationMembership.organization_id == organization.id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Update user (admin only)."""
    result = await db.execute(
        select(User).join(OrganizationMembership).where(
            User.id == user_id, OrganizationMembership.organization_id == organization.id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.username = user_data.username
    user.email = user_data.email
    user.full_name = user_data.full_name
    if user_data.password:
        user.password_hash = hash_password(user_data.password)
    membership_result = await db.execute(select(OrganizationMembership).where(
        OrganizationMembership.user_id == user.id,
        OrganizationMembership.organization_id == organization.id,
    ))
    membership = membership_result.scalar_one()
    role = UserRole.VIEWER
    if user_data.role_id:
        role_result = await db.execute(select(Role).where(Role.id == user_data.role_id, Role.is_active.is_(True)))
        role_record = role_result.scalar_one_or_none()
        if not role_record or role_record.name.lower() not in {"admin", "analyst", "viewer"}:
            raise HTTPException(status_code=400, detail="Invalid user role")
        role = UserRole(role_record.name.lower())
    user.role = role
    membership.role = {
        UserRole.ADMIN: OrganizationRole.ADMIN,
        UserRole.ANALYST: OrganizationRole.ANALYST,
        UserRole.VIEWER: OrganizationRole.VIEWER,
    }[role]
    user.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(user)

    logger.info("user_updated", user_id=user.id, updated_by=current_user.id)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Delete user (admin only)."""
    result = await db.execute(
        select(User).join(OrganizationMembership).where(
            User.id == user_id, OrganizationMembership.organization_id == organization.id
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    membership_result = await db.execute(select(OrganizationMembership).where(
        OrganizationMembership.user_id == user.id,
        OrganizationMembership.organization_id == organization.id,
    ))
    membership = membership_result.scalar_one()
    await db.delete(membership)
    other_memberships = await db.scalar(select(func.count(OrganizationMembership.id)).where(
        OrganizationMembership.user_id == user.id,
        OrganizationMembership.organization_id != organization.id,
    ))
    if not other_memberships:
        user.status = UserStatus.INACTIVE
        user.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("user_deleted", user_id=user_id, deleted_by=current_user.id)


@router.post("/mfa/setup")
async def setup_mfa(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Create a pending TOTP secret; it is not enabled until the first code is verified."""
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    current_user.mfa_secret = secret
    current_user.mfa_enabled = False
    await db.commit()
    label = urllib.parse.quote(f"SentinelWatch:{current_user.username}")
    uri = f"otpauth://totp/{label}?secret={secret}&issuer=SentinelWatch&algorithm=SHA1&digits=6&period=30"
    return {"secret": secret, "otpauth_url": uri}


@router.post("/mfa/verify")
async def verify_mfa(body: CodeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.mfa_secret or not _valid_totp(current_user.mfa_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    current_user.mfa_enabled = True
    await db.commit()
    return {"mfa_enabled": True}


@router.post("/mfa/disable")
async def disable_mfa(body: CodeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.mfa_enabled or not current_user.mfa_secret or not _valid_totp(current_user.mfa_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    await db.commit()
    return {"mfa_enabled": False}


@router.post("/password/change")
async def change_password(body: PasswordChange, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if verify_password(body.new_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Choose a different password")
    current_user.password_hash = hash_password(body.new_password)
    current_user.password_changed_at = datetime.now(timezone.utc)
    current_user.refresh_tokens = []
    await db.commit()
    return {"changed": True, "sessions_revoked": True}
