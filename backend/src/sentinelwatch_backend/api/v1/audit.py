"""
Audit Log API endpoints for SentinelWatch Backend.
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, or_, select

from ...database import get_db
from ...models import AuditLog, Organization, User
from ..deps import get_current_user, get_current_admin, get_current_analyst, get_current_organization
from ...logging import get_logger

router = APIRouter(prefix="/audit", tags=["audit"])

# Response models
class AuditLogResponse(BaseModel):
    id: str
    timestamp: datetime
    actor_type: str
    actor_id: str
    actor_name: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[dict]
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    result: str
    error_message: Optional[str]

    class Config:
        from_attributes = True


@router.get("", response_model=dict)
async def list_audit_logs(
    actor_type: Optional[str] = Query(None), actor_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None), resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None), result: Optional[str] = Query(None),
    search: Optional[str] = Query(None), start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None), page: int = Query(1, ge=1),
    skip: Optional[int] = Query(None, ge=0), limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    filters = [AuditLog.organization_id == organization.id]
    if actor_type: filters.append(AuditLog.actor_type == actor_type)
    if actor_id: filters.append(AuditLog.actor_id == actor_id)
    if action: filters.append(AuditLog.action.ilike(f"%{action}%"))
    if resource_type: filters.append(AuditLog.resource_type == resource_type)
    if resource_id: filters.append(AuditLog.resource_id == resource_id)
    if result: filters.append(AuditLog.result == result)
    if start_time: filters.append(AuditLog.timestamp >= start_time)
    if end_time: filters.append(AuditLog.timestamp <= end_time)
    if search:
        term=f"%{search}%"
        filters.append(or_(AuditLog.action.ilike(term), AuditLog.actor_name.ilike(term), AuditLog.resource_type.ilike(term)))
    total = (await db.execute(select(func.count(AuditLog.id)).where(*filters))).scalar_one()
    offset = skip if skip is not None else (page-1)*limit
    rows = (await db.execute(select(AuditLog).where(*filters).order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit))).scalars().all()
    data = [AuditLogResponse.model_validate(row, from_attributes=True).model_dump() for row in rows]
    return {"data": data, "total": total, "page": (offset//limit)+1, "page_size": limit, "total_pages": max(1,(total+limit-1)//limit)}


@router.get("/{log_id}", response_model=dict)
async def get_audit_log(
    log_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Get audit log entry by ID."""
    log = (await db.execute(select(AuditLog).where(
        AuditLog.id == log_id, AuditLog.organization_id == organization.id
    ))).scalar_one_or_none()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log entry not found"
        )
    return {
        "id": log.id,
        "timestamp": log.timestamp.isoformat(),
        "actor_type": log.actor_type,
        "actor_id": log.actor_id,
        "actor_name": log.actor_name,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "details": log.details,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "request_id": log.request_id,
        "result": log.result,
        "error_message": log.error_message,
    }


@router.get("/export/csv")
async def export_audit_csv(
    start_time: Optional[datetime] = Query(None, description="Start time"),
    end_time: Optional[datetime] = Query(None, description="End time"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Export audit logs as CSV."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    query = select(AuditLog).where(AuditLog.organization_id == organization.id)

    if start_time:
        query = query.where(AuditLog.timestamp >= start_time)
    if end_time:
        query = query.where(AuditLog.timestamp <= end_time)

    logs = (await db.execute(query.order_by(desc(AuditLog.timestamp)).limit(10000))).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "Actor Type", "Actor ID", "Actor Name",
        "Action", "Resource Type", "Resource ID",
        "IP Address", "User Agent", "Request ID",
        "Result", "Error Message"
    ])

    for log in logs:
        writer.writerow([
            log.timestamp.isoformat(),
            log.actor_type,
            log.actor_id,
            log.actor_name or "",
            log.action,
            log.resource_type or "",
            log.resource_id or "",
            log.ip_address or "",
            log.user_agent or "",
            log.request_id or "",
            log.result,
            log.error_message or "",
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit_{datetime.now().strftime('%Y%m%d')}.csv"}
    )
