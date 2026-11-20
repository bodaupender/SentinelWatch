"""
Alert Lifecycle API endpoints for SentinelWatch Backend.

Implements alert lifecycle: NEW → TRIAGED → INVESTIGATING → RESOLVED
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, or_, select

from ...database import get_db
from ...models import Alert, Evidence, Agent, User, AuditLog, Organization
from ...models.audit import AuditActorType
from ...detection_rules import DetectionEngine, ALL_RULES
from ..deps import get_current_user, get_current_analyst, get_current_organization
from ...logging import get_logger
from ...realtime import publish_organization_update

logger = get_logger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _organization_agents(organization_id: str):
    return select(Agent.id).where(Agent.organization_id == organization_id, Agent.deleted_at.is_(None))

# Request/Response models
class AlertResponse(BaseModel):
    id: str
    agent_id: str
    rule_id: Optional[str]
    rule_name: Optional[str]
    severity: str
    status: str
    mitre_techniques: Optional[list]
    mitre_tactics: Optional[list]
    correlation_key: Optional[str]
    finding_count: int
    summary: str
    description: Optional[str]
    evidence_id: Optional[str]
    assignee: Optional[str]
    triage_notes: Optional[str]
    triaged_at: Optional[datetime]
    resolution: Optional[str]
    resolution_notes: Optional[str]
    resolved_at: Optional[datetime]
    resolved_by: Optional[str]
    created_at: datetime
    updated_at: datetime
    agent_hostname: Optional[str] = None

    class Config:
        from_attributes = True


class AlertEvidenceResponse(BaseModel):
    id: str
    alert_id: str
    telemetry_type: str
    raw_records: list
    process_tree: Optional[list]
    network_connections: Optional[list]
    file_hashes: Optional[dict]
    threat_intel: Optional[dict]
    collected_at: datetime
    size_bytes: int

    class Config:
        from_attributes = True


class AlertTriageRequest(BaseModel):
    status: str
    assignee: Optional[str] = None
    notes: Optional[str] = None


class AlertResolveRequest(BaseModel):
    resolution: str
    notes: Optional[str] = None


class BulkTriageRequest(BaseModel):
    alert_ids: List[str]
    status: str
    assignee: Optional[str] = None
    notes: Optional[str] = None


@router.get("", response_model=List[AlertResponse])
async def list_alerts(
    agent_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    rule_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort: str = Query("created_at", pattern="^(created_at|severity|status)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    filters = [Alert.agent_id.in_(_organization_agents(organization.id))]
    if agent_id: filters.append(Alert.agent_id == agent_id)
    if status_filter: filters.append(Alert.status == status_filter)
    if severity: filters.append(Alert.severity == severity)
    if rule_id: filters.append(Alert.rule_id == rule_id)
    if search:
        term = f"%{search}%"
        filters.append(or_(Alert.summary.ilike(term), Alert.description.ilike(term), Alert.rule_name.ilike(term)))
    if start_time: filters.append(Alert.created_at >= start_time)
    if end_time: filters.append(Alert.created_at <= end_time)
    sort_column = getattr(Alert, sort)
    ordering = desc(sort_column) if order == "desc" else sort_column.asc()
    rows = (await db.execute(
        select(Alert, Agent.hostname).outerjoin(Agent, Alert.agent_id == Agent.id)
        .where(*filters).order_by(ordering).offset(skip).limit(limit)
    )).all()
    response = []
    for alert, hostname in rows:
        data = AlertResponse.model_validate(alert, from_attributes=True).model_dump()
        data["agent_hostname"] = hostname
        response.append(AlertResponse(**data))
    return response


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Get alert details."""
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.agent_id.in_(_organization_agents(organization.id))))).scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )

    return AlertResponse.model_validate(alert, from_attributes=True)


@router.get("/{alert_id}/evidence", response_model=AlertEvidenceResponse)
async def get_alert_evidence(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Get evidence for an alert."""
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.agent_id.in_(_organization_agents(organization.id))))).scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )

    if not alert.evidence_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No evidence found for this alert"
        )

    evidence = (await db.execute(select(Evidence).where(Evidence.id == alert.evidence_id))).scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found"
        )

    return evidence


@router.post("/{alert_id}/triage", response_model=AlertResponse)
async def triage_alert(
    alert_id: str,
    triage_data: AlertTriageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Triage an alert."""
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.agent_id.in_(_organization_agents(organization.id))))).scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )

    valid_statuses = ["new", "investigating", "true_positive", "false_positive", "benign", "resolved", "suppressed"]
    if triage_data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    previous_status = alert.status
    alert.status = triage_data.status
    alert.assignee = triage_data.assignee or current_user.username
    alert.triage_notes = triage_data.notes
    alert.triaged_at = datetime.now(timezone.utc)
    alert.updated_at = datetime.now(timezone.utc)
    db.add(AuditLog.create(
        action="alert.triaged", organization_id=organization.id,
        actor_type=AuditActorType.USER, actor_id=current_user.id,
        actor_name=current_user.username, resource_type="alert", resource_id=alert.id,
        details={"old_status": previous_status, "new_status": alert.status, "notes": triage_data.notes},
    ))

    await db.commit()
    publish_organization_update(organization.id)
    await db.refresh(alert)

    logger.info("alert_triaged", alert_id=alert_id, status=triage_data.status, assignee=current_user.username)

    return AlertResponse.from_orm(alert)


@router.post("/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    alert_id: str,
    resolve_data: AlertResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Resolve an alert."""
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.agent_id.in_(_organization_agents(organization.id))))).scalar_one_or_none()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )

    valid_resolutions = ["true_positive", "false_positive", "benign", "suppressed"]
    if resolve_data.resolution not in valid_resolutions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid resolution. Must be one of: {valid_resolutions}"
        )

    previous_status = alert.status
    alert.status = "resolved"
    alert.resolution = resolve_data.resolution
    alert.resolution_notes = resolve_data.notes
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = current_user.username
    alert.updated_at = datetime.now(timezone.utc)
    db.add(AuditLog.create(
        action="alert.resolved", organization_id=organization.id,
        actor_type=AuditActorType.USER, actor_id=current_user.id,
        actor_name=current_user.username, resource_type="alert", resource_id=alert.id,
        details={"old_status": previous_status, "new_status": alert.status,
                 "resolution": resolve_data.resolution, "notes": resolve_data.notes},
    ))

    await db.commit()
    publish_organization_update(organization.id)
    await db.refresh(alert)

    logger.info("alert_resolved", alert_id=alert_id, resolution=resolve_data.resolution, resolved_by=current_user.username)

    return AlertResponse.from_orm(alert)


@router.post("/bulk/triage", response_model=List[AlertResponse])
async def bulk_triage(
    bulk_data: BulkTriageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Triage multiple alerts at once."""
    alerts = (await db.execute(select(Alert).where(
        Alert.id.in_(bulk_data.alert_ids), Alert.agent_id.in_(_organization_agents(organization.id))
    ))).scalars().all()
    if len(alerts) != len(bulk_data.alert_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more alerts not found"
        )

    valid_statuses = ["new", "investigating", "true_positive", "false_positive", "benign", "resolved", "suppressed"]
    if bulk_data.status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    for alert in alerts:
        alert.status = bulk_data.status
        alert.assignee = bulk_data.assignee or current_user.username
        alert.triage_notes = bulk_data.notes
        alert.triaged_at = datetime.now(timezone.utc)
        alert.updated_at = datetime.now(timezone.utc)

    await db.commit()
    publish_organization_update(organization.id)

    for alert in alerts:
        await db.refresh(alert)

    logger.info("bulk_triage", alert_ids=bulk_data.alert_ids, status=bulk_data.status, assignee=current_user.username)

    return [AlertResponse.from_orm(a) for a in alerts]


@router.get("/{alert_id}/history")
async def get_alert_history(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.agent_id.in_(_organization_agents(organization.id))))).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.resource_type == "alert", AuditLog.resource_id == alert_id,
        AuditLog.organization_id == organization.id,
        AuditLog.action.in_(["alert.triaged", "alert.resolved", "alert.note_added"]),
    ).order_by(AuditLog.timestamp))).scalars().all()
    return {"history": [{
        "id": row.id, "alert_id": alert_id, "action": row.action,
        "old_status": (row.details or {}).get("old_status"),
        "new_status": (row.details or {}).get("new_status") or alert.status,
        "notes": (row.details or {}).get("notes"), "user_id": row.actor_id,
        "user_name": row.actor_name or row.actor_id, "created_at": row.timestamp,
    } for row in rows]}


@router.get("/{alert_id}/notes")
async def get_alert_notes(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.agent_id.in_(_organization_agents(organization.id))))).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    rows = (await db.execute(select(AuditLog).where(
        AuditLog.resource_type == "alert", AuditLog.resource_id == alert_id,
        AuditLog.organization_id == organization.id,
        AuditLog.action == "alert.note_added",
    ).order_by(AuditLog.timestamp.desc()))).scalars().all()
    return {"notes": [{"id": row.id, "note": (row.details or {}).get("note", ""),
                        "user_name": row.actor_name or row.actor_id, "created_at": row.timestamp}
                       for row in rows]}


@router.post("/{alert_id}/notes", status_code=status.HTTP_201_CREATED)
async def add_alert_note(
    alert_id: str,
    note_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    alert = (await db.execute(select(Alert).where(Alert.id == alert_id, Alert.agent_id.in_(_organization_agents(organization.id))))).scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    note = str(note_data.get("note", "")).strip()
    if not note or len(note) > 10000:
        raise HTTPException(status_code=400, detail="Note must contain 1 to 10000 characters")
    row = AuditLog.create(
        action="alert.note_added", organization_id=organization.id,
        actor_type=AuditActorType.USER, actor_id=current_user.id,
        actor_name=current_user.username, resource_type="alert", resource_id=alert.id,
        details={"note": note},
    )
    db.add(row)
    await db.commit()
    publish_organization_update(organization.id)
    await db.refresh(row)
    return {"id": row.id, "note": note, "user_name": row.actor_name, "created_at": row.timestamp}


@router.get("/stats/summary")
async def get_alert_stats(
    start_time: Optional[datetime] = Query(None, description="Start time"),
    end_time: Optional[datetime] = Query(None, description="End time"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Get alert statistics using the async database session."""
    filters = [Alert.agent_id.in_(_organization_agents(organization.id))]
    if start_time:
        filters.append(Alert.created_at >= start_time)
    if end_time:
        filters.append(Alert.created_at <= end_time)

    total = (await db.execute(select(func.count(Alert.id)).where(*filters))).scalar_one()
    by_severity = dict((await db.execute(
        select(Alert.severity, func.count(Alert.id)).where(*filters).group_by(Alert.severity)
    )).all())
    by_status = dict((await db.execute(
        select(Alert.status, func.count(Alert.id)).where(*filters).group_by(Alert.status)
    )).all())
    return {"total": total, "by_severity": by_severity, "by_status": by_status}
