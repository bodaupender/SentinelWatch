"""
Agent/Endpoint API endpoints for SentinelWatch Backend.
"""

from typing import Optional, List
import secrets
from copy import deepcopy
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, desc, asc, or_

from ...database import get_db
from ...models import Agent, Organization, ProcessTelemetry, ServiceTelemetry, StartupInventory, EventLogEntry, User
from ...config import get_config
from ...logging import get_logger
from ..deps import get_current_user, get_current_analyst, get_current_organization, get_current_organization_admin
from ...realtime import publish_organization_update
from sqlalchemy import select

router = APIRouter(prefix="/agents", tags=["agents"])
logger = get_logger(__name__)

# Request/Response models
class AgentRegister(BaseModel):
    hostname: str
    machine_guid: str
    os_version: str
    agent_version: str
    enrollment_token: str
    tags: Optional[str] = None

class AgentResponse(BaseModel):
    id: str
    hostname: str
    machine_guid: str
    os_version: str
    agent_version: str
    ip_address: Optional[str]
    status: str
    last_seen: Optional[datetime]
    last_heartbeat: Optional[datetime]
    config_version: int
    tags: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentDetailResponse(AgentResponse):
    config_applied_at: Optional[datetime]
    assigned_config: Optional[dict]
    health_data: Optional[dict]
    health_alerts: Optional[list]


class AgentConfigUpdate(BaseModel):
    collection_intervals: Optional[dict] = None
    batching: Optional[dict] = None
    eventlog_channels: Optional[list] = None
    eventlog_event_ids: Optional[list] = None
    process: Optional[dict] = None
    service: Optional[dict] = None
    startup: Optional[dict] = None
    redaction: Optional[dict] = None

    @field_validator("collection_intervals")
    @classmethod
    def validate_collection_intervals(cls, value):
        if value is None:
            return value
        bounds = {
            "process": (3, 300), "service": (5, 3600), "startup": (30, 86400),
            "eventlog": (1, 3600), "health": (5, 3600),
            "heartbeat": (5, 300), "config": (10, 3600),
        }
        unknown = set(value) - bounds.keys()
        if unknown:
            raise ValueError(f"Unsupported collection interval(s): {', '.join(sorted(unknown))}")
        for name, interval in value.items():
            minimum, maximum = bounds[name]
            if isinstance(interval, bool) or not isinstance(interval, int) or not minimum <= interval <= maximum:
                raise ValueError(f"{name} interval must be an integer from {minimum} to {maximum} seconds")
        return value


class AgentConfigResponse(BaseModel):
    collection_intervals: dict
    batching: dict
    eventlog_channels: list
    eventlog_event_ids: list
    process: dict
    service: dict
    startup: dict
    redaction: dict
    config_version: int
    signature: str


def _reported_status(agent: Agent) -> str:
    heartbeat = agent.last_heartbeat or agent.last_seen
    if not heartbeat:
        stored_status = getattr(agent.status, "value", agent.status)
        if stored_status == "unregistered":
            return "unregistered"
        return "offline"
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    if age_seconds <= 180:
        return "online"
    if age_seconds <= 900:
        return "stale"
    return "offline"


def _effective_agent_config(agent: Agent) -> tuple[dict, int]:
    """Return endpoint overrides or the server defaults with a matching version."""
    server_config = get_config().agent_config
    if isinstance(agent.assigned_config, dict):
        return agent.assigned_config, agent.config_version
    return server_config.model_dump(), max(agent.config_version, server_config.version)


@router.post("/register", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    agent_data: AgentRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Admin-only compatibility registration with the configured enrollment secret."""
    config = get_config()
    if not config.server.debug:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Metadata-only registration is disabled. Create an organization enrollment token and enroll the endpoint with the agent.",
        )
    if not config.agent_enrollment_token:
        raise HTTPException(status_code=503, detail="Agent enrollment is not configured")
    if not secrets.compare_digest(agent_data.enrollment_token, config.agent_enrollment_token):
        raise HTTPException(status_code=401, detail="Invalid enrollment token")

    # Check if agent already exists
    result = await db.execute(select(Agent).filter(Agent.machine_guid == agent_data.machine_guid))
    existing = result.scalar_one_or_none()

    if existing:
        if existing.organization_id != organization.id:
            raise HTTPException(status_code=409, detail="Endpoint identity is already enrolled")
        # Update existing agent
        existing.hostname = agent_data.hostname
        existing.os_version = agent_data.os_version
        existing.agent_version = agent_data.agent_version
        existing.enrollment_token = None
        if not existing.last_heartbeat:
            existing.status = "unregistered"
        await db.commit()
        await db.refresh(existing)
        logger.info("agent_updated", agent_id=existing.id)
        return existing

    # Create new agent
    agent = Agent(
        hostname=agent_data.hostname,
        machine_guid=agent_data.machine_guid,
        agent_version=agent_data.agent_version,
        organization_id=organization.id,
        enrollment_token=None,
        tags=agent_data.tags,
        status="unregistered",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    logger.info("agent_registered", agent_id=agent.id, hostname=agent.hostname)
    return agent


@router.get("", response_model=dict)
async def list_agents(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search hostname"),
    status: Optional[str] = Query(None, description="Status filter used by the UI"),
    page: int = Query(1, ge=1),
    skip: Optional[int] = Query(None, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    sort: str = Query("last_seen", pattern="^(last_seen|hostname|status|os_version)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    db = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    """List registered agents using the UI's paginated response contract."""
    filters = [Agent.organization_id == organization.id, Agent.deleted_at.is_(None)]

    selected_status = (status_filter or status or "").lower()
    now = datetime.now(timezone.utc)
    online_cutoff = now - timedelta(seconds=180)
    stale_cutoff = now - timedelta(seconds=900)
    if selected_status == "online":
        filters.append(func.lower(Agent.status) == "online")
        filters.append(or_(Agent.last_heartbeat >= online_cutoff,
                           Agent.last_heartbeat.is_(None) & (Agent.last_seen >= online_cutoff)))
    elif selected_status == "stale":
        filters.extend([func.lower(Agent.status) == "online", Agent.last_heartbeat < online_cutoff,
                        Agent.last_heartbeat >= stale_cutoff])
    elif selected_status == "offline":
        filters.append(or_(func.lower(Agent.status) != "online", Agent.last_heartbeat.is_(None),
                           Agent.last_heartbeat < stale_cutoff))

    if search:
        filters.append(Agent.hostname.ilike(f"%{search}%"))

    total = await db.scalar(select(func.count(Agent.id)).where(*filters)) or 0
    offset = skip if skip is not None else (page - 1) * limit
    sort_column = getattr(Agent, sort)
    sort_order = desc(sort_column) if order == "desc" else asc(sort_column)
    result = await db.execute(
        select(Agent).where(*filters).order_by(sort_order).offset(offset).limit(limit)
    )
    agents = result.scalars().all()
    data = []
    for agent in agents:
        item = AgentResponse.model_validate(agent, from_attributes=True).model_dump()
        item["status"] = _reported_status(agent)
        data.append(item)
    return {
        "data": data,
        "total": total,
        "page": page if skip is None else offset // limit + 1,
        "page_size": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    """Get agent details."""
    result = await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    ))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    item = AgentDetailResponse.model_validate(agent, from_attributes=True).model_dump()
    item["status"] = _reported_status(agent)
    return item


@router.get("/{agent_id}/config", response_model=AgentConfigResponse)
async def get_agent_config(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    """Get agent configuration."""
    result = await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    ))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    agent_config, config_version = _effective_agent_config(agent)

    return AgentConfigResponse(
        collection_intervals=agent_config["collection_intervals"],
        batching=agent_config["batching"],
        eventlog_channels=agent_config["eventlog_channels"],
        eventlog_event_ids=agent_config["eventlog_event_ids"],
        process=agent_config["process"],
        service=agent_config["service"],
        startup=agent_config["startup"],
        redaction=agent_config["redaction"],
        config_version=config_version,
        signature="placeholder",  # Would be signed in production
    )


@router.put("/{agent_id}/config", response_model=AgentConfigResponse)
async def update_agent_config(
    agent_id: str,
    config_update: AgentConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Update agent configuration."""
    result = await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    ))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    # Merge config updates
    current_config, _ = _effective_agent_config(agent)
    updated_config = deepcopy(current_config)

    if config_update.collection_intervals:
        updated_config["collection_intervals"].update(config_update.collection_intervals)
    if config_update.batching:
        updated_config["batching"].update(config_update.batching)
    if config_update.eventlog_channels:
        updated_config["eventlog_channels"] = config_update.eventlog_channels
    if config_update.eventlog_event_ids:
        updated_config["eventlog_event_ids"] = config_update.eventlog_event_ids
    if config_update.process:
        updated_config["process"].update(config_update.process)
    if config_update.service:
        updated_config["service"].update(config_update.service)
    if config_update.startup:
        updated_config["startup"].update(config_update.startup)
    if config_update.redaction:
        updated_config["redaction"].update(config_update.redaction)

    agent.assigned_config = updated_config
    agent.config_version = max(agent.config_version + 1, get_config().agent_config.version + 1)
    agent.config_applied_at = datetime.now(timezone.utc)
    await db.commit()

    # Sign config (placeholder)
    import json
    config_json = json.dumps(updated_config, sort_keys=True)
    signature = "placeholder_signature"  # Would use Ed25519 in production

    logger.info("agent_config_updated", agent_id=agent_id, updated_by=current_user.id)

    return AgentConfigResponse(
        collection_intervals=updated_config["collection_intervals"],
        batching=updated_config["batching"],
        eventlog_channels=updated_config["eventlog_channels"],
        eventlog_event_ids=updated_config["eventlog_event_ids"],
        process=updated_config["process"],
        service=updated_config["service"],
        startup=updated_config["startup"],
        redaction=updated_config["redaction"],
        config_version=agent.config_version,
        signature=signature,
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization_admin),
):
    """Unenroll agent."""
    result = await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    ))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    # Soft delete
    agent.deleted_at = datetime.now(timezone.utc)
    agent.status = "offline"
    agent.credential_version += 1
    await db.commit()
    publish_organization_update(organization.id)

    logger.info("agent_deleted", agent_id=agent_id, deleted_by=current_user.id)


@router.get("/{agent_id}/health", response_model=dict)
async def get_agent_health(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization: Organization = Depends(get_current_organization),
):
    """Get agent health metrics."""
    result = await db.execute(select(Agent).where(
        Agent.id == agent_id, Agent.organization_id == organization.id, Agent.deleted_at.is_(None)
    ))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    return agent.health_data or {}
