"""
Reports API endpoints for SentinelWatch Backend.
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import func, select, desc

from ...database import get_db
from ...models import Alert, Agent, AgentCredential, ProcessTelemetry, ServiceTelemetry, EventLogEntry, AuditLog, Organization, User
from ..deps import get_current_user, get_current_analyst, get_current_organization
from .agents import _reported_status
from ...logging import get_logger

router = APIRouter(prefix="/reports", tags=["reports"])


# Response models
class AlertReport(BaseModel):
    total_alerts: int
    by_severity: dict
    by_status: dict
    by_agent: dict
    by_rule: dict
    timeline: list


class EndpointReport(BaseModel):
    total_endpoints: int
    by_status: dict
    by_os: dict
    by_version: dict
    alerts_per_endpoint: dict


class InvestigationExport(BaseModel):
    alert_id: str
    alert_data: dict
    evidence: dict
    related_events: list
    investigation_notes: list
    generated_at: datetime


@router.get("/alerts", response_model=dict)
async def get_alert_report(
    start_time: Optional[datetime] = Query(None, description="Start time"),
    end_time: Optional[datetime] = Query(None, description="End time"),
    agent_id: Optional[str] = Query(None, description="Filter by agent"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Generate an alert report from the async database session."""
    organization_agents = select(Agent.id).where(
        Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    )
    filters = [Alert.agent_id.in_(organization_agents)]
    if start_time:
        filters.append(Alert.created_at >= start_time)
    if end_time:
        filters.append(Alert.created_at <= end_time)
    if agent_id:
        filters.append(Alert.agent_id == agent_id)

    total = (await db.execute(select(func.count(Alert.id)).where(*filters))).scalar_one()
    by_severity = dict((await db.execute(
        select(Alert.severity, func.count(Alert.id)).where(*filters).group_by(Alert.severity)
    )).all())
    by_status = dict((await db.execute(
        select(Alert.status, func.count(Alert.id)).where(*filters).group_by(Alert.status)
    )).all())
    by_agent = dict((await db.execute(
        select(Agent.hostname, func.count(Alert.id))
        .join(Alert, Alert.agent_id == Agent.id)
        .where(*filters)
        .group_by(Agent.hostname)
    )).all())
    by_rule = dict((await db.execute(
        select(Alert.rule_id, func.count(Alert.id)).where(*filters).group_by(Alert.rule_id)
    )).all())

    end = end_time or datetime.now(timezone.utc)
    start = start_time or (end - timedelta(hours=24))
    timestamps = (await db.execute(
        select(Alert.created_at).where(*filters, Alert.created_at >= start, Alert.created_at <= end)
    )).scalars().all()
    hourly_counts = {}
    for timestamp in timestamps:
        hour = timestamp.replace(minute=0, second=0, microsecond=0)
        hourly_counts[hour.isoformat()] = hourly_counts.get(hour.isoformat(), 0) + 1

    return {
        "total_alerts": total,
        "by_severity": by_severity,
        "by_status": by_status,
        "by_agent": by_agent,
        "by_rule": by_rule,
        "timeline": [{"hour": hour, "count": count} for hour, count in sorted(hourly_counts.items())],
    }


@router.get("/endpoints", response_model=dict)
async def get_endpoint_report(
    start_time: Optional[datetime] = Query(None, description="Start time"),
    end_time: Optional[datetime] = Query(None, description="End time"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Generate endpoint inventory report."""
    filters = [Agent.organization_id == organization.id, Agent.deleted_at.is_(None)]
    if start_time:
        filters.append(Agent.created_at >= start_time)
    if end_time:
        filters.append(Agent.created_at <= end_time)

    total = (await db.execute(select(func.count(Agent.id)).where(*filters))).scalar_one()
    agents = (await db.execute(select(Agent).where(*filters))).scalars().all()
    enrolled = (await db.execute(
        select(func.count(Agent.id))
        .join(AgentCredential, AgentCredential.agent_id == Agent.id)
        .where(
            *filters,
            AgentCredential.credential_version == Agent.credential_version,
            AgentCredential.revoked_at.is_(None),
        )
    )).scalar_one()
    by_status: dict[str, int] = {}
    for agent in agents:
        reported_status = _reported_status(agent)
        by_status[reported_status] = by_status.get(reported_status, 0) + 1
    by_os = dict((await db.execute(
        select(Agent.os_version, func.count(Agent.id)).where(*filters).group_by(Agent.os_version)
    )).all())
    by_version = dict((await db.execute(
        select(Agent.agent_version, func.count(Agent.id)).where(*filters).group_by(Agent.agent_version)
    )).all())
    alerts_per_endpoint = dict((await db.execute(
        select(Alert.agent_id, func.count(Alert.id))
        .where(Alert.agent_id.in_(select(Agent.id).where(*filters)),
               Alert.created_at >= datetime.now(timezone.utc) - timedelta(days=7))
        .group_by(Alert.agent_id)
    )).all())

    return {
        "total_endpoints": total,
        "enrolled_endpoints": enrolled,
        "unregistered_endpoints": total - enrolled,
        "by_status": by_status,
        "by_os": by_os,
        "by_version": by_version,
        "alerts_per_endpoint": alerts_per_endpoint,
    }


@router.get("/investigation/{alert_id}", response_model=dict)
async def export_investigation(
    alert_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Export investigation data for an alert."""
    from ...models import Evidence, EventLogEntry, AuditLog

    alert = db.query(Alert).join(Agent, Agent.id == Alert.agent_id).filter(
        Alert.id == alert_id, Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    ).first()
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found"
        )

    evidence = alert.evidence
    related_events = db.query(EventLogEntry).filter(
        EventLogEntry.agent_id == alert.agent_id,
        EventLogEntry.event_timestamp >= alert.created_at - timedelta(hours=1),
        EventLogEntry.event_timestamp <= alert.created_at + timedelta(hours=1),
    ).all()

    investigation_notes = db.query(AuditLog).filter(
        AuditLog.resource_type == "alert",
        AuditLog.resource_id == alert_id,
    ).all()

    return {
        "alert_id": alert.id,
        "alert_data": {
            "id": alert.id,
            "summary": alert.summary,
            "severity": alert.severity,
            "status": alert.status,
            "rule_name": alert.rule_name,
            "created_at": alert.created_at.isoformat(),
            "agent_hostname": alert.agent.hostname if alert.agent else None,
        },
        "evidence": evidence.raw_records if evidence else {},
        "related_events": [
            {
                "event_id": e.event_id,
                "timestamp": e.event_timestamp.isoformat(),
                "source": e.source,
                "message": e.message,
            }
            for e in related_events
        ],
        "investigation_notes": [
            {
                "timestamp": n.timestamp.isoformat(),
                "action": n.action,
                "actor": n.actor_name,
                "details": n.details,
            }
            for n in investigation_notes
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/alerts/export")
async def export_alerts_csv(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    severity: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Export alerts as CSV."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    query = db.query(Alert).join(Agent, Agent.id == Alert.agent_id).filter(
        Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    )

    if start_time:
        query = query.filter(Alert.created_at >= start_time)
    if end_time:
        query = query.filter(Alert.created_at <= end_time)
    if severity:
        query = query.filter(Alert.severity == severity)
    if status_filter:
        query = query.filter(Alert.status == status_filter)

    alerts = query.order_by(Alert.created_at.desc()).limit(10000).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Alert ID", "Rule ID", "Rule Name", "Severity", "Status",
        "Agent", "Summary", "Created At", "Updated At",
        "Resolved At", "Resolution", "Assignee"
    ])

    for alert in alerts:
        writer.writerow([
            alert.id,
            alert.rule_id or "",
            alert.rule_name or "",
            alert.severity,
            alert.status,
            alert.agent.hostname if alert.agent else "",
            alert.summary,
            alert.created_at.isoformat(),
            alert.updated_at.isoformat(),
            alert.resolved_at.isoformat() if alert.resolved_at else "",
            alert.resolution or "",
            alert.assignee or "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=alerts_{datetime.now().strftime('%Y%m%d')}.csv"}
    )
