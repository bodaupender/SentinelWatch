"""
Detection Rules API endpoints for SentinelWatch Backend.
"""

from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import Rule, Organization, User
from ...detection_rules import ALL_RULES
from ...detection_rules.rule_model import DetectionRule
from ..deps import get_current_user, get_current_admin, get_current_analyst, get_current_organization
from ...logging import get_logger

router = APIRouter(prefix="/rules", tags=["rules"])

# Request/Response models
class RuleResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    rule_type: str
    condition: str
    condition_version: int
    status: str
    severity: str
    mitre_techniques: Optional[list]
    mitre_tactics: Optional[list]
    tags: Optional[list]
    version: int
    previous_version_id: Optional[str]
    promoted_from_staging_at: Optional[datetime]
    promoted_by: Optional[str]
    author: Optional[str]
    owner: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RuleCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    rule_type: str
    condition: str
    severity: str
    status: str = "draft"
    mitre_techniques: Optional[list] = None
    mitre_tactics: Optional[list] = None
    tags: Optional[list] = None
    condition_version: int = 1


class RuleUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    condition: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    mitre_techniques: Optional[list] = None
    mitre_tactics: Optional[list] = None
    tags: Optional[list] = None


class RuleTestRequest(BaseModel):
    telemetry: dict
    expected: bool


class RuleTestResponse(BaseModel):
    rule_id: str
    rule_name: str
    matched: bool
    result: Optional[dict] = None


@router.get("", response_model=List[dict])
async def list_rules(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type"),
    search: Optional[str] = Query(None, description="Search by name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """List detection rules with filtering and pagination."""
    query = select(Rule).where(Rule.organization_id == organization.id)

    if status_filter:
        query = query.filter(Rule.status == status_filter)
    if rule_type:
        query = query.filter(Rule.rule_type == rule_type)
    if search:
        query = query.filter(Rule.display_name.ilike(f"%{search}%") | Rule.name.ilike(f"%{search}%"))

    result = await db.execute(query.order_by(Rule.name).offset(skip).limit(limit))
    rules = result.scalars().all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "display_name": r.display_name,
            "description": r.description,
            "rule_type": r.rule_type,
            "severity": r.severity,
            "status": r.status,
            "mitre_techniques": r.mitre_techniques,
            "tags": r.tags,
            "version": r.version,
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        }
        for r in rules
    ]


@router.get("/builtin", response_model=List[dict])
async def list_builtin_rules(
    category: Optional[str] = Query(None, description="Filter by category"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    current_user: User = Depends(get_current_analyst),
):
    """List built-in detection rules from the detection engine."""
    from ...detection_rules import ALL_RULES
    from ...detection_rules.rule_model import DetectionRule

    rules = ALL_RULES

    if category:
        rules = [r for r in rules if r.category == category]
    if severity:
        rules = [r for r in rules if r.severity == severity]

    return [
        {
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "description": r.description,
            "category": r.category,
            "severity": r.severity,
            "confidence": r.confidence,
            "condition": r.condition,
            "mitre_techniques": r.mitre_techniques,
            "evidence_requirements": r.evidence_requirements,
            "investigation_guidance": r.investigation_guidance,
            "false_positive_rate": r.false_positive_rate,
            "enabled": r.enabled,
        }
        for r in rules
    ]


@router.get("/{rule_id}", response_model=dict)
async def get_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Get rule details."""
    # First check database
    result = await db.execute(select(Rule).where(
        Rule.id == rule_id, Rule.organization_id == organization.id
    ))
    rule = result.scalar_one_or_none()
    if rule:
        return {
            "id": rule.id,
            "name": rule.name,
            "display_name": rule.display_name,
            "description": rule.description,
            "rule_type": rule.rule_type,
            "condition": rule.condition,
            "condition_version": rule.condition_version,
            "severity": rule.severity,
            "status": rule.status,
            "mitre_techniques": rule.mitre_techniques,
            "mitre_tactics": rule.mitre_tactics,
            "tags": rule.tags,
            "version": rule.version,
            "previous_version_id": rule.previous_version_id,
            "promoted_from_staging_at": rule.promoted_from_staging_at,
            "promoted_by": rule.promoted_by,
            "author": rule.author,
            "owner": rule.owner,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }
    # Fallback to built-in rules
    for rule in ALL_RULES:
        if rule.rule_id == rule_id:
            return {
                "id": rule.rule_id,
                "name": rule.rule_id,
                "display_name": rule.rule_name,
                "description": rule.description,
                "rule_type": rule.category,
                "severity": rule.severity,
                "status": "active" if rule.enabled else "inactive",
                "mitre_techniques": rule.mitre_techniques,
                "mitre_tactics": rule.mitre_tactics,
                "tags": [],
                "version": 1,
                "created_at": None,
                "updated_at": None,
            }
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Rule not found"
    )

@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_rule(
    rule_data: RuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Create a new custom detection rule."""
    rule = Rule(
        organization_id=organization.id,
        name=rule_data.name,
        display_name=rule_data.display_name,
        description=rule_data.description,
        rule_type=rule_data.rule_type,
        condition=rule_data.condition,
        condition_version=rule_data.condition_version,
        severity=rule_data.severity,
        status=rule_data.status,
        mitre_techniques=rule_data.mitre_techniques,
        mitre_tactics=rule_data.mitre_tactics,
        tags=rule_data.tags,
        author=current_user.username,
        owner=current_user.username,
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    logger.info("rule_created", rule_id=rule.id, name=rule.name, created_by=current_user.username)

    return {
        "id": rule.id,
        "name": rule.name,
        "display_name": rule.display_name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "severity": rule.severity,
        "status": rule.status,
        "created_at": rule.created_at,
    }


@router.put("/{rule_id}", response_model=dict)
async def update_rule(
    rule_id: str,
    rule_data: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Update a custom detection rule."""
    result = await db.execute(select(Rule).where(
        Rule.id == rule_id, Rule.organization_id == organization.id
    ))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )

    # Check if rule is builtin (no previous_version_id means custom)
    if rule.previous_version_id is None and rule.id != rule_id:
        # This is a builtin rule, can't modify
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify built-in rules. Create a custom version instead."
        )

    # Update fields
    if rule_data.display_name is not None:
        rule.display_name = rule_data.display_name
    if rule_data.description is not None:
        rule.description = rule_data.description
    if rule_data.condition is not None:
        rule.condition = rule_data.condition
        rule.condition_version += 1
    if rule_data.severity is not None:
        rule.severity = rule_data.severity
    if rule_data.status is not None:
        rule.status = rule_data.status
    if rule_data.mitre_techniques is not None:
        rule.mitre_techniques = rule_data.mitre_techniques
    if rule_data.mitre_tactics is not None:
        rule.mitre_tactics = rule_data.mitre_tactics
    if rule_data.tags is not None:
        rule.tags = rule_data.tags

    await db.commit()
    await db.refresh(rule)

    logger.info("rule_updated", rule_id=rule.id, updated_by=current_user.id)

    return {
        "id": rule.id,
        "name": rule.name,
        "display_name": rule.display_name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "condition": rule.condition,
        "condition_version": rule.condition_version,
        "severity": rule.severity,
        "status": rule.status,
        "mitre_techniques": rule.mitre_techniques,
        "mitre_tactics": rule.mitre_tactics,
        "tags": rule.tags,
        "version": rule.version,
        "previous_version_id": rule.previous_version_id,
        "promoted_from_staging_at": rule.promoted_from_staging_at,
        "promoted_by": rule.promoted_by,
        "author": rule.author,
        "owner": rule.owner,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }

    rule.version += 1
    rule.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(rule)

    logger.info("rule_updated", rule_id=rule.id, updated_by=current_user.username)

    return {
        "id": rule.id,
        "name": rule.name,
        "display_name": rule.display_name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "severity": rule.severity,
        "status": rule.status,
        "version": rule.version,
        "updated_at": rule.updated_at,
    }


@router.post("/{rule_id}/test", response_model=RuleTestResponse)
async def test_rule(
    rule_id: str,
    test_data: RuleTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Test a rule against sample telemetry data."""
    result = await db.execute(select(Rule).where(
        Rule.id == rule_id, Rule.organization_id == organization.id
    ))
    rule = result.scalar_one_or_none()

    # Also check builtin rules
    if not rule:
        from ...detection_rules import ALL_RULES
        rule_obj = None
        for r in ALL_RULES:
            if r.rule_id == rule_id:
                rule_obj = r
                break
        if not rule_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rule not found"
            )

            # Test with builtin rule
            from ...detection_rules.rule_model import DetectionEngine
            engine = DetectionEngine([rule_obj])
            results = engine.evaluate(test_data.telemetry)

            matched = len(results) > 0
            result = results[0] if results else None

            return RuleTestResponse(
                rule_id=rule_id,
                rule_name=rule_obj.rule_name,
                matched=matched,
                result=result.to_alert_dict() if result else None,
            )

    # Test with custom rule
    from ...detection_rules.rule_model import DetectionEngine
    engine = DetectionEngine([rule])
    results = engine.evaluate(test_data.telemetry)

    matched = len(results) > 0
    result = results[0] if results else None

    return RuleTestResponse(
        rule_id=rule_id,
        rule_name=rule.name,
        matched=matched,
        result=result.to_alert_dict() if result else None,
    )


@router.post("/{rule_id}/promote", response_model=dict)
async def promote_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Promote a rule from staging to active."""
    result = await db.execute(select(Rule).where(
        Rule.id == rule_id, Rule.organization_id == organization.id
    ))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )

    rule.status = "active"
    rule.promoted_from_staging_at = datetime.now(timezone.utc)
    rule.promoted_by = current_user.username
    rule.updated_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info("rule_promoted", rule_id=rule_id, promoted_by=current_user.username)

    return {"message": "Rule promoted to active", "rule_id": rule_id}


@router.post("/{rule_id}/demote", response_model=dict)
async def demote_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Demote a rule from active to staging."""
    result = await db.execute(select(Rule).where(
        Rule.id == rule_id, Rule.organization_id == organization.id
    ))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )

    rule.status = "staging"
    rule.updated_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info("rule_demoted", rule_id=rule_id, demoted_by=current_user.username)

    return {"message": "Rule demoted to staging", "rule_id": rule_id}


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
    organization: Organization = Depends(get_current_organization),
):
    """Delete a custom detection rule."""
    result = await db.execute(select(Rule).where(
        Rule.id == rule_id, Rule.organization_id == organization.id
    ))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )

    # Prevent deletion of builtin rules
    if rule.previous_version_id is None and rule.id != rule_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete built-in rules"
        )

    await db.delete(rule)
    await db.commit()

    logger.info("rule_deleted", rule_id=rule_id, deleted_by=current_user.username)
