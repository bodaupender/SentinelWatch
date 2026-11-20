"""
Telemetry API endpoints for SentinelWatch Backend.
"""

from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, desc, select, or_, false

from ...database import get_db
from ...models import ProcessTelemetry, ServiceTelemetry, StartupInventory, EventLogEntry, Agent, Organization, User
from ..deps import get_current_user, get_current_analyst, get_current_organization
from ...logging import get_logger

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


def _organization_agents(organization_id: str):
    return select(Agent.id).where(
        Agent.organization_id == organization_id,
        Agent.deleted_at.is_(None),
    )


def _classify_snapshot_freshness(snapshots, check_time: datetime):
    normalized = [
        (agent_id, latest_at if latest_at.tzinfo else latest_at.replace(tzinfo=timezone.utc))
        for agent_id, latest_at in snapshots
    ]
    reporting = [
        (agent_id, latest_at)
        for agent_id, latest_at in normalized
        if (check_time - latest_at).total_seconds() <= 180
    ]
    newest = max((latest_at for _, latest_at in normalized), default=None)
    return reporting, newest, len(normalized) - len(reporting)


async def _latest_snapshot_window(
    db: AsyncSession, model, organization_id: str, agent_id: Optional[str] = None
):
    latest_query = (
        select(model.agent_id, func.max(model.collected_at).label("latest_at"))
        .join(Agent, Agent.id == model.agent_id)
        .where(Agent.organization_id == organization_id, Agent.deleted_at.is_(None))
        .group_by(model.agent_id)
    )
    if agent_id:
        latest_query = latest_query.where(model.agent_id == agent_id)
    snapshots = (await db.execute(latest_query)).all()
    check_time = datetime.now(timezone.utc)
    reporting_snapshots, snapshot_at, stale_agents = _classify_snapshot_freshness(snapshots, check_time)
    conditions = []
    for current_agent_id, latest_at in reporting_snapshots:
        conditions.append(
            and_(model.agent_id == current_agent_id,
                 # A large machine may take longer than one collection interval
                 # to enumerate. Keep a bounded minute so a scan isn't cut in half.
                 model.collected_at >= latest_at - timedelta(seconds=60))
        )
    if not conditions:
        # An empty condition list would expose the entire telemetry history, which
        # would make old records look current when every agent has stopped reporting.
        conditions.append(false())
    return conditions, snapshot_at, not reporting_snapshots, len(reporting_snapshots), stale_agents

# Response models
class ProcessTelemetryResponse(BaseModel):
    id: str
    agent_id: str
    collected_at: datetime
    observed_at: Optional[datetime]
    terminated_at: Optional[datetime]
    ingested_at: Optional[datetime]
    sequence: int
    pid: int
    ppid: int
    name: str
    cmdline: Optional[str]
    exe: Optional[str]
    username: Optional[str]
    create_time: Optional[datetime]
    cpu_percent: Optional[float]
    memory_percent: Optional[float]
    num_threads: Optional[int] = None
    num_handles: Optional[int] = None
    status: Optional[str] = None
    memory_rss_mb: Optional[float] = None
    agent_hostname: Optional[str] = None
    connections: Optional[list]
    exe_sha256: Optional[str]
    integrity_level: Optional[str]

    class Config:
        from_attributes = True


class ServiceTelemetryResponse(BaseModel):
    id: str
    agent_id: str
    collected_at: datetime
    sequence: int
    name: str
    display_name: Optional[str]
    description: Optional[str] = None
    status: str
    start_type: str
    pid: Optional[int] = None
    binary_path: Optional[str]
    service_type: Optional[str]
    dependencies: Optional[list]
    account: Optional[str]
    exe_sha256: Optional[str]

    class Config:
        from_attributes = True


class StartupInventoryResponse(BaseModel):
    id: str
    agent_id: str
    collected_at: datetime
    sequence: int
    source: str
    name: str
    command: Optional[str]
    user_context: Optional[str]
    enabled: bool
    exe_sha256: Optional[str]

    class Config:
        from_attributes = True


class EventLogEntryResponse(BaseModel):
    id: str
    agent_id: str
    collected_at: datetime
    sequence: int
    event_id: int
    record_id: int
    source: str
    level: str
    computer: str
    message: Optional[str]
    extracted: Optional[dict]
    event_timestamp: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/processes", response_model=dict)
async def list_processes(
    agent_id: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    pid: Optional[int] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=1000),
    skip: Optional[int] = Query(None, ge=0),
    sort: str = Query("collected_at", pattern="^(collected_at|pid|name|cpu_percent|memory_percent)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """List real process telemetry with the pagination shape used by the UI."""
    snapshot_filters, snapshot_at, is_stale, reporting_agents, stale_agents = await _latest_snapshot_window(db, ProcessTelemetry, organization.id, agent_id)
    filters = [ProcessTelemetry.agent_id.in_(_organization_agents(organization.id)), *snapshot_filters]
    if agent_id: filters.append(ProcessTelemetry.agent_id == agent_id)
    if name: filters.append(ProcessTelemetry.name.ilike(f"%{name}%"))
    if username: filters.append(ProcessTelemetry.username.ilike(f"%{username}%"))
    if pid is not None: filters.append(ProcessTelemetry.pid == pid)
    if start_time: filters.append(ProcessTelemetry.collected_at >= start_time)
    if end_time: filters.append(ProcessTelemetry.collected_at <= end_time)
    if search:
        term = f"%{search}%"
        filters.append(or_(ProcessTelemetry.name.ilike(term), ProcessTelemetry.cmdline.ilike(term), ProcessTelemetry.exe.ilike(term)))

    ranked = select(
        ProcessTelemetry.id.label("id"),
        func.row_number().over(
            partition_by=(ProcessTelemetry.agent_id, ProcessTelemetry.pid, ProcessTelemetry.create_time),
            order_by=desc(ProcessTelemetry.collected_at),
        ).label("row_number"),
        ProcessTelemetry.terminated_at.label("terminated_at"),
    ).where(*filters).subquery()
    total = (await db.execute(
        select(func.count()).select_from(ranked).where(
            ranked.c.row_number == 1,
            ranked.c.terminated_at.is_(None),
        )
    )).scalar_one()
    sort_column = getattr(ProcessTelemetry, sort, ProcessTelemetry.collected_at)
    sort_order = desc(sort_column) if order == "desc" else sort_column.asc()
    offset = skip if skip is not None else (page - 1) * limit
    rows = (await db.execute(
        select(ProcessTelemetry, Agent.hostname)
        .outerjoin(Agent, ProcessTelemetry.agent_id == Agent.id)
        .join(ranked, and_(ProcessTelemetry.id == ranked.c.id, ranked.c.row_number == 1))
        .where(*filters, ProcessTelemetry.terminated_at.is_(None))
        .order_by(sort_order).offset(offset).limit(limit)
    )).all()

    data = []
    for record, hostname in rows:
        item = ProcessTelemetryResponse.model_validate(record, from_attributes=True).model_dump()
        item["agent_hostname"] = hostname
        item["memory_rss_mb"] = record.memory_rss_bytes / (1024 * 1024) if record.memory_rss_bytes is not None else None
        data.append(item)
    page_number = page if skip is None else (offset // limit) + 1
    return {
        "data": data,
        "total": total,
        "page": page_number,
        "page_size": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
        "snapshot_at": snapshot_at,
        "is_stale": is_stale,
        "reporting_agents": reporting_agents,
        "stale_agents": stale_agents,
    }


@router.get("/processes/stats/summary", response_model=dict)
async def get_process_stats(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Count process telemetry records in the selected dashboard period."""
    filters = [ProcessTelemetry.agent_id.in_(_organization_agents(organization.id))]
    if start_time: filters.append(ProcessTelemetry.collected_at >= start_time)
    if end_time: filters.append(ProcessTelemetry.collected_at <= end_time)
    total = (await db.execute(select(func.count(ProcessTelemetry.id)).where(*filters))).scalar_one()
    return {"process_records": total}


@router.get("/processes/export")
async def export_processes_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Export recent process telemetry for the signed-in analyst."""
    import csv
    import io

    rows = (await db.execute(
        select(ProcessTelemetry, Agent.hostname)
        .join(Agent, ProcessTelemetry.agent_id == Agent.id)
        .where(Agent.organization_id == organization.id, Agent.deleted_at.is_(None))
        .order_by(desc(ProcessTelemetry.collected_at)).limit(10000)
    )).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Collected At", "Agent", "PID", "Parent PID", "Process", "User", "CPU %", "Memory MB", "Executable", "Command Line", "SHA-256"])
    for record, hostname in rows:
        writer.writerow([
            record.collected_at.isoformat(), hostname or "", record.pid, record.ppid,
            record.name, record.username or "", record.cpu_percent or 0,
            round(record.memory_rss_bytes / (1024 * 1024), 2) if record.memory_rss_bytes is not None else "",
            record.exe or "", record.cmdline or "", record.exe_sha256 or "",
        ])
    return Response(
        content=output.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sentinelwatch-processes.csv"},
    )


@router.get("/processes/tree", response_model=dict)
async def get_process_tree(
    agent_id: str = Query(..., description="Agent ID"),
    pid: int = Query(..., description="Root PID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    result = await db.execute(
        select(ProcessTelemetry.id).join(Agent, Agent.id == ProcessTelemetry.agent_id).where(
            ProcessTelemetry.agent_id == agent_id,
            Agent.organization_id == organization.id,
            Agent.deleted_at.is_(None),
        )
        .order_by(desc(ProcessTelemetry.collected_at)).limit(1)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No telemetry found for agent")
    return {"root_pid": pid, "agent_id": agent_id, "processes": []}


@router.get("/processes/{telemetry_id}", response_model=ProcessTelemetryResponse)
async def get_process(
    telemetry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    result = await db.execute(
        select(ProcessTelemetry)
        .join(Agent, Agent.id == ProcessTelemetry.agent_id)
        .where(ProcessTelemetry.id == telemetry_id, Agent.organization_id == organization.id)
    )
    process = result.scalar_one_or_none()
    if not process:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process telemetry not found")
    item = ProcessTelemetryResponse.model_validate(process, from_attributes=True).model_dump()
    item["memory_rss_mb"] = process.memory_rss_bytes / (1024 * 1024) if process.memory_rss_bytes is not None else None
    return item


@router.get("/services", response_model=dict)
async def list_services(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    name: Optional[str] = Query(None, description="Filter by service name"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    start_type: Optional[str] = Query(None, description="Filter by start type"),
    page: int = Query(1, ge=1),
    skip: Optional[int] = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    sort: str = Query("collected_at", pattern="^(collected_at|name|status|start_type)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """List service telemetry with filtering and pagination."""
    snapshot_filters, snapshot_at, is_stale, reporting_agents, stale_agents = await _latest_snapshot_window(db, ServiceTelemetry, organization.id, agent_id)
    filters = [ServiceTelemetry.agent_id.in_(_organization_agents(organization.id)), *snapshot_filters]

    if name:
        filters.append(ServiceTelemetry.name.ilike(f"%{name}%"))
    if status_filter:
        filters.append(func.lower(ServiceTelemetry.status) == status_filter.lower())
    if start_type:
        filters.append(func.lower(ServiceTelemetry.start_type) == start_type.lower())

    ranked = select(
        ServiceTelemetry.id.label("id"),
        func.row_number().over(
            partition_by=(ServiceTelemetry.agent_id, ServiceTelemetry.name),
            order_by=desc(ServiceTelemetry.collected_at),
        ).label("row_number"),
    ).where(*filters).subquery()
    total = (await db.execute(
        select(func.count()).select_from(ranked).where(ranked.c.row_number == 1)
    )).scalar_one()
    offset = skip if skip is not None else (page - 1) * limit
    sort_column = getattr(ServiceTelemetry, sort)
    sort_order = desc(sort_column) if order == "desc" else sort_column.asc()
    rows = (await db.execute(
        select(ServiceTelemetry, Agent.hostname)
        .outerjoin(Agent, ServiceTelemetry.agent_id == Agent.id)
        .join(ranked, and_(ServiceTelemetry.id == ranked.c.id, ranked.c.row_number == 1))
        .where(*filters).order_by(sort_order).offset(offset).limit(limit)
    )).all()
    data = []
    for service, hostname in rows:
        item = ServiceTelemetryResponse.model_validate(service, from_attributes=True).model_dump()
        item["agent_hostname"] = hostname
        data.append(item)
    return {
        "data": data, "total": total,
        "page": page if skip is None else offset // limit + 1,
        "page_size": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
        "snapshot_at": snapshot_at,
        "is_stale": is_stale,
        "reporting_agents": reporting_agents,
        "stale_agents": stale_agents,
    }


@router.get("/services/export")
async def export_services_csv(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """Export the latest observed service state for each endpoint."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    snapshot_filters, _, _, _, _ = await _latest_snapshot_window(db, ServiceTelemetry, organization.id)
    ranked = select(
        ServiceTelemetry.id.label("id"),
        func.row_number().over(
            partition_by=(ServiceTelemetry.agent_id, ServiceTelemetry.name),
            order_by=desc(ServiceTelemetry.collected_at),
        ).label("row_number"),
    ).where(*snapshot_filters).subquery()
    rows = (await db.execute(
        select(ServiceTelemetry, Agent.hostname)
        .outerjoin(Agent, ServiceTelemetry.agent_id == Agent.id)
        .join(ranked, and_(ServiceTelemetry.id == ranked.c.id, ranked.c.row_number == 1))
        .order_by(ServiceTelemetry.name)
    )).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Endpoint", "Service", "Display Name", "Status", "Start Type", "Binary Path", "Account", "Collected At"])
    for service, hostname in rows:
        writer.writerow([hostname or "", service.name, service.display_name or "", service.status,
                         service.start_type, service.binary_path or "", service.account or "",
                         service.collected_at.isoformat()])
    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=sentinelwatch-services.csv"
    })


@router.get("/services/{telemetry_id}", response_model=ServiceTelemetryResponse)
async def get_service(
    telemetry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    """Get service telemetry by ID."""
    service = (await db.execute(
        select(ServiceTelemetry)
        .join(Agent, Agent.id == ServiceTelemetry.agent_id)
        .where(ServiceTelemetry.id == telemetry_id, Agent.organization_id == organization.id)
    )).scalar_one_or_none()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service telemetry not found"
        )
    return service


@router.get("/startup", response_model=list[StartupInventoryResponse])
async def list_startup(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    source: Optional[str] = Query(None, description="Filter by source"),
    enabled: Optional[bool] = Query(None, description="Filter by enabled status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """List startup inventory with filtering and pagination."""
    query = select(StartupInventory).where(
        StartupInventory.agent_id.in_(_organization_agents(organization.id))
    )

    if agent_id:
        query = query.where(StartupInventory.agent_id == agent_id)
    if source:
        query = query.where(StartupInventory.source == source)
    if enabled is not None:
        query = query.where(StartupInventory.enabled == enabled)

    results = await db.execute(query.order_by(desc(StartupInventory.collected_at)).offset(skip).limit(limit))
    return results.scalars().all()


@router.get("/startup/{telemetry_id}", response_model=StartupInventoryResponse)
async def get_startup(
    telemetry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    """Get startup inventory by ID."""
    startup = (await db.execute(
        select(StartupInventory)
        .join(Agent, Agent.id == StartupInventory.agent_id)
        .where(StartupInventory.id == telemetry_id, Agent.organization_id == organization.id)
    )).scalar_one_or_none()
    if not startup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Startup inventory not found"
        )
    return startup


@router.get("/events", response_model=dict)
async def list_events(
    agent_id: Optional[str] = Query(None),
    event_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    skip: Optional[int] = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    sort: str = Query("event_timestamp", pattern="^(event_timestamp|event_id|channel|level)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_analyst),
    organization: Organization = Depends(get_current_organization),
):
    """List Windows event telemetry in the paginated shape used by the UI."""
    filters = [EventLogEntry.agent_id.in_(_organization_agents(organization.id))]
    if agent_id:
        filters.append(EventLogEntry.agent_id == agent_id)
    if event_id is not None:
        filters.append(EventLogEntry.event_id == event_id)
    channel_filter = channel or source
    if channel_filter:
        filters.append(EventLogEntry.source.ilike(f"%{channel_filter}%"))
    if level:
        filters.append(EventLogEntry.level.ilike(level))
    if start_time:
        filters.append(EventLogEntry.event_timestamp >= start_time)
    if end_time:
        filters.append(EventLogEntry.event_timestamp <= end_time)
    if search:
        term = f"%{search}%"
        filters.append(or_(EventLogEntry.source.ilike(term), EventLogEntry.message.ilike(term), EventLogEntry.computer.ilike(term)))

    total = await db.scalar(select(func.count()).select_from(EventLogEntry).where(*filters)) or 0
    sort_column = {
        "event_timestamp": EventLogEntry.event_timestamp,
        "event_id": EventLogEntry.event_id,
        "channel": EventLogEntry.source,
        "level": EventLogEntry.level,
    }[sort]
    ordering = sort_column.asc() if order == "asc" else sort_column.desc()
    offset = skip if skip is not None else (page - 1) * limit
    result = await db.execute(
        select(EventLogEntry).where(*filters).order_by(ordering).offset(offset).limit(limit)
    )
    rows = result.scalars().all()
    agent_ids = {row.agent_id for row in rows}
    hostnames = {}
    if agent_ids:
        agents_result = await db.execute(select(Agent.id, Agent.hostname).where(
            Agent.id.in_(agent_ids), Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
        ))
        hostnames = {agent_id: hostname for agent_id, hostname in agents_result.all()}
    data = [{
        "id": row.id,
        "agent_id": row.agent_id,
        "agent_hostname": hostnames.get(row.agent_id),
        "collected_at": row.collected_at,
        "sequence": row.sequence,
        "event_id": row.event_id,
        "record_id": row.record_id,
        "channel": row.source,
        "provider_name": (row.extracted or {}).get("provider_name", row.source),
        "source": row.source,
        "level": row.level,
        "computer": row.computer,
        "message": row.message or "",
        "raw_xml": row.raw_xml or "",
        "extracted": row.extracted or {},
        "event_timestamp": row.event_timestamp or row.collected_at,
        "user_sid": (row.extracted or {}).get("user_sid", ""),
        "user_name": (row.extracted or {}).get("user_name", ""),
        "user_domain": (row.extracted or {}).get("user_domain", ""),
        "process_id": (row.extracted or {}).get("process_id", 0),
        "process_name": (row.extracted or {}).get("process_name", ""),
        "process_command_line": (row.extracted or {}).get("process_command_line", ""),
        "parent_process_id": (row.extracted or {}).get("parent_process_id", 0),
        "parent_process_name": (row.extracted or {}).get("parent_process_name", ""),
        "process_hash_sha256": "",
    } for row in rows]
    return {"data": data, "total": total, "page": page, "page_size": limit, "total_pages": (total + limit - 1) // limit}


@router.get("/events/{telemetry_id}", response_model=EventLogEntryResponse)
async def get_event(
    telemetry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    """Get event log entry by ID."""
    event = (await db.execute(
        select(EventLogEntry)
        .join(Agent, Agent.id == EventLogEntry.agent_id)
        .where(EventLogEntry.id == telemetry_id, Agent.organization_id == organization.id)
    )).scalar_one_or_none()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event log entry not found"
        )
    return event
