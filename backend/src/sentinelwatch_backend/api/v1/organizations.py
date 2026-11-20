"""Organization inventory and membership administration endpoints."""

import re
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_db
from ...models import Organization, OrganizationMembership, OrganizationRole, User
from ..deps import get_current_user, get_current_organization_admin

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class MemberChange(BaseModel):
    user_id: str
    role: str = "viewer"


class MemberRoleChange(BaseModel):
    role: str


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:80] or "organization"
    return f"{base}-{secrets.token_hex(4)}"


@router.get("", response_model=list[dict])
async def list_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Organization, OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(OrganizationMembership.user_id == current_user.id)
        .order_by(Organization.name)
    )
    return [
        {"id": organization.id, "name": organization.name, "slug": organization.slug,
         "role": role.value if hasattr(role, "value") else role}
        for organization, role in result.all()
    ]


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_organization(
    payload: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    organization = Organization(name=payload.name.strip(), slug=_slug(payload.name))
    membership = OrganizationMembership(
        organization=organization, user=current_user, role=OrganizationRole.OWNER
    )
    db.add_all([organization, membership])
    await db.commit()
    await db.refresh(organization)
    return {"id": organization.id, "name": organization.name, "slug": organization.slug, "role": "owner"}


@router.get("/{organization_id}/members", response_model=list[dict])
async def list_members(
    organization_id: str,
    db: AsyncSession = Depends(get_db),
    organization: Organization = Depends(get_current_organization_admin),
):
    if organization.id != organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    result = await db.execute(
        select(User, OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
        .where(OrganizationMembership.organization_id == organization.id)
        .order_by(User.username)
    )
    return [
        {"id": user.id, "username": user.username, "email": user.email,
         "full_name": user.full_name, "role": role.value if hasattr(role, "value") else role}
        for user, role in result.all()
    ]


@router.post("/{organization_id}/members", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_member(
    organization_id: str,
    payload: MemberChange,
    db: AsyncSession = Depends(get_db),
    organization: Organization = Depends(get_current_organization_admin),
):
    if organization.id != organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        role = OrganizationRole(payload.role.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Role must be admin, analyst, or viewer")
    if role == OrganizationRole.OWNER:
        raise HTTPException(status_code=400, detail="Use owner transfer to assign ownership")

    user = await db.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Active user not found")
    existing = await db.scalar(select(OrganizationMembership.id).where(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == user.id,
    ))
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member")
    membership = OrganizationMembership(organization_id=organization.id, user_id=user.id, role=role)
    db.add(membership)
    await db.commit()
    return {"user_id": user.id, "organization_id": organization.id, "role": role.value}


@router.patch("/{organization_id}/members/{user_id}", response_model=dict)
async def update_member_role(
    organization_id: str,
    user_id: str,
    payload: MemberRoleChange,
    db: AsyncSession = Depends(get_db),
    organization: Organization = Depends(get_current_organization_admin),
    current_user: User = Depends(get_current_user),
):
    if organization.id != organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        role = OrganizationRole(payload.role.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid organization role")
    result = await db.execute(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == user_id,
    ))
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Organization member not found")
    if membership.role == OrganizationRole.OWNER and role != OrganizationRole.OWNER:
        owners = await db.scalar(select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.role == OrganizationRole.OWNER,
        ))
        if owners <= 1:
            raise HTTPException(status_code=409, detail="Transfer ownership before removing the last owner")
    if role == OrganizationRole.OWNER and membership.role != OrganizationRole.OWNER:
        raise HTTPException(status_code=400, detail="Owner transfer is not implemented yet")
    membership.role = role
    await db.commit()
    return {"user_id": user_id, "organization_id": organization.id, "role": role.value}


@router.delete("/{organization_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    organization_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    organization: Organization = Depends(get_current_organization_admin),
    current_user: User = Depends(get_current_user),
):
    if organization.id != organization_id:
        raise HTTPException(status_code=404, detail="Organization not found")
    result = await db.execute(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization.id,
        OrganizationMembership.user_id == user_id,
    ))
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Organization member not found")
    if membership.role == OrganizationRole.OWNER:
        owners = await db.scalar(select(func.count(OrganizationMembership.id)).where(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.role == OrganizationRole.OWNER,
        ))
        if owners <= 1:
            raise HTTPException(status_code=409, detail="Transfer ownership before removing the last owner")
    await db.delete(membership)
    await db.commit()
