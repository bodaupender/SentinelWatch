"""
Suppression API endpoints for SentinelWatch Backend.

Manages alert suppression rules and allowlists.
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import func, desc

from ...database import get_db
from ...models import Organization, SuppressionRule, User
from ..deps import get_current_user, get_current_organization_admin
from ...logging import get_logger

router = APIRouter(prefix="/suppressions", tags=["suppressions"])

# Response models
class SuppressionRuleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    rule_type: str  # "alert", "rule", "agent", "global"
    target_id: Optional[str]
    target_type: Optional[str]
    condition: str
    severity: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    created_by: str

    class Config:
        from_attributes = True


class SuppressionRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rule_type: str  # "alert", "rule", "agent", "global"
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    condition: str
    severity: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_active: bool = True


class SuppressionRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    condition: Optional[str] = None
    severity: Optional[str] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


router = APIRouter(prefix="/suppressions", tags=["suppressions"])


@router.get("", response_model=list)
async def list_suppressions(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """List suppression rules."""
    query = select(SuppressionRule).where(SuppressionRule.organization_id == organization.id)

    if is_active is not None:
        query = query.where(SuppressionRule.is_active == is_active)
    if rule_type:
        query = query.where(SuppressionRule.rule_type == rule_type)

    result = await db.execute(query.order_by(SuppressionRule.created_at.desc()).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_suppression(
    rule_data: SuppressionRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Create a new suppression rule."""
    rule = SuppressionRule(
        organization_id=organization.id,
        name=rule_data.name,
        description=rule_data.description,
        rule_type=rule_data.rule_type,
        target_id=rule_data.target_id,
        target_type=rule_data.target_type,
        condition=rule_data.condition,
        severity=rule_data.severity,
        is_active=rule_data.is_active,
        expires_at=rule_data.expires_at,
        created_by=current_user.username,
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    logger.info("suppression_created", rule_id=rule.id, name=rule.name, created_by=current_user.username)

    return {"id": rule.id, "name": rule.name, "message": "Suppression rule created"}


@router.get("/{suppression_id}", response_model=dict)
async def get_suppression(
    suppression_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Get suppression rule by ID."""
    rule = (await db.execute(select(SuppressionRule).where(
        SuppressionRule.id == suppression_id, SuppressionRule.organization_id == organization.id
    ))).scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suppression rule not found"
        )
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "target_id": rule.target_id,
        "target_type": rule.target_type,
        "condition": rule.condition,
        "severity": rule.severity,
        "is_active": rule.is_active,
        "expires_at": rule.expires_at.isoformat() if rule.expires_at else None,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
        "created_by": rule.created_by,
    }


@router.put("/{suppression_id}", response_model=dict)
async def update_suppression(
    suppression_id: str,
    update_data: SuppressionRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Update a suppression rule."""
    rule = (await db.execute(select(SuppressionRule).where(
        SuppressionRule.id == suppression_id, SuppressionRule.organization_id == organization.id
    ))).scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suppression rule not found"
        )

    if update_data.name is not None:
        rule.name = update_data.name
    if update_data.description is not None:
        rule.description = update_data.description
    if update_data.condition is not None:
        rule.condition = update_data.condition
    if update_data.severity is not None:
        rule.severity = update_data.severity
    if update_data.is_active is not None:
        rule.is_active = update_data.is_active
    if update_data.expires_at is not None:
        rule.expires_at = update_data.expires_at

    rule.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(rule)

    logger.info("suppression_updated", rule_id=rule.id, updated_by=current_user.username)

    return {"id": rule.id, "name": rule.name, "message": "Suppression rule updated"}


@router.delete("/{suppression_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_suppression(
    suppression_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Delete a suppression rule."""
    rule = (await db.execute(select(SuppressionRule).where(
        SuppressionRule.id == suppression_id, SuppressionRule.organization_id == organization.id
    ))).scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suppression rule not found"
        )

    await db.delete(rule)
    await db.commit()

    logger.info("suppression_deleted", rule_id=suppression_id, deleted_by=current_user.username)
