"""
Agent Communication API endpoints for SentinelWatch Backend.

Implements secure agent-to-backend communication:
- Agent authentication and registration
- Telemetry ingestion
- Configuration distribution
- Heartbeat handling
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
import re
import secrets
import uuid as uuid_mod

from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, Field
from sqlalchemy import func, desc, update, case, or_

from ...database import get_db
from ...models import Agent, AgentCredential, EnrollmentToken, EnrollmentTokenStatus, ProcessTelemetry, ServiceTelemetry, StartupInventory, EventLogEntry, AgentHealth, User
from ...config import get_config
from ...auth import decode_token, create_access_token
from ...logging import get_logger
from ...realtime import publish_organization_update
from ...security.config_signing import sign_config as _sign_config
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/agent/v1", tags=["agent-communication"])

AGENT_ACCESS_TOKEN_TTL = timedelta(minutes=15)
AGENT_REFRESH_TOKEN_TTL = timedelta(days=90)


def _sign_config_for_agent(config_data: dict, version: int) -> str:
    """Sign a config blob for this agent so it can verify integrity client-side."""
    secret = get_config().auth.jwt_secret.encode("utf-8")
    payload = {"v": version, "c": config_data}
    return _sign_config(payload, secret)


def _effective_agent_config(agent: Agent) -> tuple[dict, int]:
    """Return endpoint overrides when present, otherwise server defaults."""
    server_config = get_config().agent_config
    if isinstance(agent.assigned_config, dict):
        return agent.assigned_config, agent.config_version
    return server_config.model_dump(), max(agent.config_version, server_config.version)

logger = get_logger(__name__)


def _record_to_telemetry_dict(record, telemetry_type: str) -> Optional[Dict[str, Any]]:
    """Convert a DB-orm record to a flat telemetry dict for rule evaluation.

    Normalises collector field names into canonical rule-facing names and
    redacts command-line content so credentials are never stored in alerts.
    """
    if record is None:
        return None

    import json

    base = {}
    try:
        base = {k: v for k, v in record.__dict__.items() if not k.startswith('_')}
    except Exception:
        pass

    if telemetry_type == "process":
        # Canonicalise names used by process detection rules
        canon: Dict[str, Any] = {
            "source": "process",
            "process_name": base.get("name"),
            "process_exe": base.get("exe"),
            "parent_process_name": base.get("parent_name"),
            "parent_process_exe": base.get("parent_exe"),
            "process_pid": base.get("pid"),
            "parent_pid": base.get("ppid"),
            "process_username": base.get("username"),
            "process_integrity_level": base.get("integrity_level"),
            "is_signed": base.get("is_signed") or False,
            "sequence": base.get("sequence"),
        }
        cmdline = base.get("cmdline")
        # Redact common credential tokens from command lines before storing
        if cmdline:
            redacted = cmdline
            for token in ("--password", "-p", "--secret", "token=", "password="):
                redacted = re.sub(re.escape(token) + r"\s*\S+", f"{token} **REDACTED**", redacted, flags=re.IGNORECASE)
            canon["process_cmdline"] = redacted
        else:
            canon["process_cmdline"] = None
        if base.get("exe_sha256"):
            canon["file_hash_sha256"] = base["exe_sha256"]

    elif telemetry_type == "service":
        canon = {
            "source": "service",
            "service_name": base.get("name"),
            "service_display_name": base.get("display_name"),
            "service_binary_path": base.get("binary_path"),
            "service_account": base.get("account"),
            "service_start_type": base.get("start_type"),
            "service_status": base.get("status"),
            "sequence": base.get("sequence"),
        }
        if base.get("exe_sha256"):
            canon["file_hash_sha256"] = base["exe_sha256"]
        bp = base.get("binary_path") or ""
        canon.setdefault("service_binary_directory", os.path.dirname(str(bp)))

    elif telemetry_type == "startup":
        canon = {
            "source": "startup",
            "startup_source": base.get("source"),
            "startup_name": base.get("name"),
            "startup_command": base.get("command"),
            "startup_entry": base.get("name"),
            "startup_executable_path": base.get("exe"),
            "startup_user_context": base.get("user_context"),
            "sequence": base.get("sequence"),
        }
        if base.get("exe_sha256"):
            canon["file_hash_sha256"] = base["exe_sha256"]

    elif telemetry_type == "eventlog":
        extracted = base.get("extracted") or {}
        canon = {
            "source": "eventlog",
            "event_log_event_id": base.get("event_id"),
            "event_log_source": base.get("source"),
            "event_log_message": base.get("message"),
            "sequence": base.get("sequence"),
            "extracted": extracted,
        }
        for key, val in list(extracted.items()):
            canon.setdefault(f"event_{key}", val)

    else:
        canon = {"source": telemetry_type, **base}

    canon["collected_at"] = base.get("collected_at")
    canon["observed_at"] = base.get("observed_at")
    canon["agent_id"] = base.get("agent_id")
    return canon


def agent_credential_is_current(payload: Dict[str, Any], agent: Optional[Agent]) -> bool:
    """Check that a signed agent token still matches the active credential generation."""
    return bool(
        agent is not None
        and agent.deleted_at is None
        and payload.get("type") == "agent"
        and payload.get("sub") == agent.id
        and payload.get("credential_version", 0) == agent.credential_version
    )


# Request/Response models
class AgentRegistrationRequest(BaseModel):
    """Agent registration request from agent."""
    hostname: str
    machine_guid: str
    os_version: str
    agent_version: str
    enrollment_token: str
    csr: Optional[str] = None  # Certificate signing request
    tags: Optional[str] = None


class AgentRegistrationResponse(BaseModel):
    agent_id: str
    agent_token: str
    agent_refresh_token: str
    client_certificate: Optional[str] = None
    ca_certificate: Optional[str] = None
    config: Dict[str, Any]
    config_signature: str
    config_version: int


class HeartbeatRequest(BaseModel):
    """Agent heartbeat request."""
    agent_id: str
    health: Dict[str, Any]
    version: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentTokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=40, max_length=128)


class AgentTokenRefreshResponse(BaseModel):
    agent_token: str
    agent_refresh_token: str
    expires_in_seconds: int


class HeartbeatResponse(BaseModel):
    config_update_available: bool
    config_version: int
    message: str = "OK"


class TelemetryBatchRequest(BaseModel):
    """Batch telemetry submission from agent."""
    agent_id: str
    telemetry_type: str  # process, service, startup, eventlog
    batch: List[Dict[str, Any]]
    compressed: bool = False
    sequence: int


class TelemetryBatchResponse(BaseModel):
    accepted: int
    rejected: int
    alerts_created: int
    next_sequence: int


class ConfigPollRequest(BaseModel):
    """Agent configuration poll request."""
    agent_id: str
    current_config_version: int


class ConfigPollResponse(BaseModel):
    config_update_available: bool
    config: Optional[Dict[str, Any]] = None
    config_signature: Optional[str] = None
    config_version: int


class AgentHealthResponse(BaseModel):
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    disk_free_gb: float
    disk_total_gb: float
    network_bytes_sent: int
    network_bytes_recv: int
    queue_depth: int
    batches_sent: int
    batches_failed: int
    events_sent: int
    events_rejected: int


class ReEnrollmentRequest(BaseModel):
    """Agent re-enrollment request."""
    agent_id: str
    machine_guid: str
    hostname: str
    os_version: str
    agent_version: str
    enrollment_token: str
    csr: Optional[str] = None


class ReEnrollmentResponse(BaseModel):
    agent_id: str
    agent_token: str
    agent_refresh_token: str
    client_certificate: Optional[str] = None
    ca_certificate: Optional[str] = None
    config: Dict[str, Any]
    config_signature: str
    config_version: int


async def get_agent_from_token(db: AsyncSession, token: str) -> Optional[Agent]:
    """Extract agent from authorization token."""
    try:
        payload = decode_token(token)
        agent_id = payload.get("sub")
        if not agent_id or payload.get("type") != "agent":
            return None
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.deleted_at.is_(None)))
        agent = result.scalar_one_or_none()
        if not agent_credential_is_current(payload, agent):
            return None
        return agent
    except Exception:
        return None


def hash_agent_refresh_token(token: str) -> str:
    """Hash an opaque refresh token before storing or querying it."""
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _make_agent_access_token(agent: Agent) -> str:
    return create_access_token(
        {
            "sub": agent.id,
            "role": "agent",
            "type": "agent",
            "credential_version": agent.credential_version,
        },
        expires_delta=AGENT_ACCESS_TOKEN_TTL,
    )


async def _rotate_agent_refresh_token(db: AsyncSession, agent: Agent) -> str:
    """Replace the agent's only refresh token, invalidating any previous value."""
    now = datetime.now(timezone.utc)
    raw_token = secrets.token_urlsafe(48)
    result = await db.execute(
        select(AgentCredential)
        .where(AgentCredential.agent_id == agent.id)
        .with_for_update()
    )
    credential = result.scalar_one_or_none()
    if credential is None:
        credential = AgentCredential(
            agent_id=agent.id,
            token_hash=hash_agent_refresh_token(raw_token),
            credential_version=agent.credential_version,
            expires_at=now + AGENT_REFRESH_TOKEN_TTL,
            created_at=now,
            rotated_at=now,
            revoked_at=None,
        )
        db.add(credential)
    else:
        credential.token_hash = hash_agent_refresh_token(raw_token)
        credential.credential_version = agent.credential_version
        credential.expires_at = now + AGENT_REFRESH_TOKEN_TTL
        credential.rotated_at = now
        credential.revoked_at = None
    return raw_token


@router.post("/token/refresh", response_model=AgentTokenRefreshResponse)
async def refresh_agent_token(
    request: AgentTokenRefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Atomically rotate a refresh token and return a short-lived access token."""
    now = datetime.now(timezone.utc)
    old_hash = hash_agent_refresh_token(request.refresh_token)
    result = await db.execute(
        select(AgentCredential, Agent)
        .join(Agent, Agent.id == AgentCredential.agent_id)
        .where(
            AgentCredential.token_hash == old_hash,
            AgentCredential.revoked_at.is_(None),
            AgentCredential.expires_at > now,
            Agent.deleted_at.is_(None),
        )
        .with_for_update()
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked agent refresh token",
        )

    credential, agent = row
    if credential.credential_version != agent.credential_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent credential has been rotated or revoked",
        )

    new_raw_token = secrets.token_urlsafe(48)
    update_result = await db.execute(
        update(AgentCredential)
        .where(
            AgentCredential.id == credential.id,
            AgentCredential.token_hash == old_hash,
            AgentCredential.revoked_at.is_(None),
            AgentCredential.expires_at > now,
            AgentCredential.credential_version == agent.credential_version,
        )
        .values(
            token_hash=hash_agent_refresh_token(new_raw_token),
            expires_at=now + AGENT_REFRESH_TOKEN_TTL,
            rotated_at=now,
        )
    )
    if update_result.rowcount != 1:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent refresh token was already used",
        )

    await db.commit()
    return AgentTokenRefreshResponse(
        agent_token=_make_agent_access_token(agent),
        agent_refresh_token=new_raw_token,
        expires_in_seconds=int(AGENT_ACCESS_TOKEN_TTL.total_seconds()),
    )


async def _resolve_enrollment_token(db: AsyncSession, raw_token: str):
    """Resolve a one-time organization token, or a legacy local-development token."""
    result = await db.execute(
        select(EnrollmentToken)
        .where(EnrollmentToken.token_hash == EnrollmentToken.hash_token(raw_token))
        .with_for_update()
    )
    enrollment = result.scalar_one_or_none()
    if enrollment is not None:
        if not enrollment.is_valid() or not enrollment.organization_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired enrollment token")
        return enrollment, enrollment.organization_id

    # Preserve the existing single-organization local installer flow. This configured
    # bootstrap secret can only enroll into the migration's legacy tenant.
    configured_token = get_config().agent_enrollment_token
    if get_config().server.debug and configured_token and secrets.compare_digest(raw_token, configured_token):
        return None, "00000000-0000-4000-8000-000000000001"
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired enrollment token")


async def _consume_enrollment_token(db: AsyncSession, enrollment: EnrollmentToken, agent_id: str) -> None:
    """Atomically redeem an active token so concurrent enrollments cannot exceed max_uses."""
    now = datetime.now(timezone.utc)
    # Normalize expires_at to UTC for comparison.
    # Handles both naive datetimes (from SQLite) and timezone-aware datetimes.
    expires_at = enrollment.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        # Already timezone-aware: convert to UTC if not already
        expires_at = expires_at.astimezone(timezone.utc)
    statement = (
        update(EnrollmentToken)
        .where(
            EnrollmentToken.id == enrollment.id,
            EnrollmentToken.status == EnrollmentTokenStatus.ACTIVE,
            EnrollmentToken.used_count < EnrollmentToken.max_uses,
            or_(EnrollmentToken.expires_at.is_(None), expires_at > now),
        )
        .values(
            used_count=EnrollmentToken.used_count + 1,
            used_at=now,
            used_by_agent_id=agent_id,
            status=case(
                (EnrollmentToken.used_count + 1 >= EnrollmentToken.max_uses, EnrollmentTokenStatus.USED),
                else_=EnrollmentTokenStatus.ACTIVE,
            ),
        )
    )
    result = await db.execute(statement)
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid, expired, or redeemed enrollment token")


@router.post("/register", response_model=AgentRegistrationResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    request: AgentRegistrationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new agent endpoint or re-enroll existing."""
    enrollment, organization_id = await _resolve_enrollment_token(db, request.enrollment_token)

    # Check if agent already exists by machine_guid
    result = await db.execute(select(Agent).filter(Agent.machine_guid == request.machine_guid))
    existing = result.scalar_one_or_none()
    if existing and existing.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Endpoint identity is already enrolled")

    # Also check for duplicate hostname with different machine_guid (copied VM scenario)
    hostname_conflict = await db.execute(
        select(Agent).filter(
            Agent.hostname == request.hostname,
            Agent.machine_guid != request.machine_guid,
            Agent.organization_id == organization_id,
            Agent.deleted_at.is_(None)
        )
    )
    conflicting_hostname = hostname_conflict.scalar_one_or_none()

    if existing:
        # Verify hostname consistency
        if existing.hostname != request.hostname:
            logger.warning(
                "hostname_changed",
                agent_id=existing.id,
                old_hostname=existing.hostname,
                new_hostname=request.hostname,
            )

        existing.enrollment_token = None
        existing.hostname = request.hostname
        existing.os_version = request.os_version
        existing.agent_version = request.agent_version
        existing.deleted_at = None
        existing.credential_version += 1
        existing.last_seen = datetime.now(timezone.utc)
        existing.last_heartbeat = datetime.now(timezone.utc)
        existing.enrolled_at = datetime.now(timezone.utc)
        existing.status = "online"
        refresh_token = await _rotate_agent_refresh_token(db, existing)
        if enrollment:
            await _consume_enrollment_token(db, enrollment, existing.id)
        await db.commit()
        await db.refresh(existing)
        publish_organization_update(existing.organization_id)
        logger.info("agent_re_enrolled", agent_id=existing.id, hostname=request.hostname)

        config_data, config_version = _effective_agent_config(existing)
        return AgentRegistrationResponse(
            agent_id=existing.id,
            agent_token=_make_agent_access_token(existing),
            agent_refresh_token=refresh_token,
            client_certificate=None,
            ca_certificate=None,
            config=config_data,
            config_signature=_sign_config_for_agent(config_data, config_version),
            config_version=config_version,
        )

    if conflicting_hostname:
        # Same hostname, different machine_guid - likely a copied VM
        logger.warning(
            "potential_copied_vm_detected",
            existing_agent_id=conflicting_hostname.id,
            existing_machine_guid=conflicting_hostname.machine_guid,
            new_machine_guid=request.machine_guid,
            hostname=request.hostname,
        )
        # Create new agent but log the conflict - backend admin must review
        # We allow registration but mark it for review

    # Create new agent
    agent = Agent(
        hostname=request.hostname,
        machine_guid=request.machine_guid,
        os_version=request.os_version,
        agent_version=request.agent_version,
        organization_id=organization_id,
        enrollment_token=None,
        enrolled_at=datetime.now(timezone.utc),
        tags=request.tags,
        status="online",
        last_seen=datetime.now(timezone.utc),
        last_heartbeat=datetime.now(timezone.utc),
    )

    db.add(agent)
    await db.flush()
    refresh_token = await _rotate_agent_refresh_token(db, agent)
    if enrollment:
        await _consume_enrollment_token(db, enrollment, agent.id)
    await db.commit()
    await db.refresh(agent)
    publish_organization_update(agent.organization_id)

    # This local bearer-token flow does not claim to issue an mTLS certificate.
    client_cert = None
    ca_cert = None

    logger.info("agent_registered", agent_id=agent.id, hostname=request.hostname)

    # Return configuration
    config_data, config_version = _effective_agent_config(agent)
    return AgentRegistrationResponse(
        agent_id=agent.id,
        agent_token=_make_agent_access_token(agent),
        agent_refresh_token=refresh_token,
        client_certificate=client_cert,
        ca_certificate=ca_cert,
        config=config_data,
        config_signature=_sign_config_for_agent(config_data, config_version),
        config_version=config_version,
    )


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def agent_heartbeat(
    request: HeartbeatRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Agent heartbeat endpoint."""
    # Verify agent token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = authorization[7:]  # Remove "Bearer "
    agent = await get_agent_from_token(db, token)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired agent token"
        )

    # Update agent status
    agent.last_seen = datetime.now(timezone.utc)
    agent.last_heartbeat = datetime.now(timezone.utc)
    agent.status = "online"
    agent.health_data = request.health
    agent.health_alerts = []

    await db.commit()
    publish_organization_update(agent.organization_id)

    # Check if config update needed
    _, config_version = _effective_agent_config(agent)
    config_update = request.health.get("config_version", 0) < config_version

    return HeartbeatResponse(
        config_update_available=config_update,
        config_version=config_version,
    )


@router.post("/telemetry", response_model=TelemetryBatchResponse)
async def submit_telemetry(
    request: TelemetryBatchRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Receive telemetry batch from agent."""
    # Import telemetry models at function start to avoid scoping issues
    from ...models.telemetry import ProcessTelemetry, ServiceTelemetry, StartupInventory, EventLogEntry

    # Verify agent token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = authorization[7:]
    agent = await get_agent_from_token(db, token)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired agent token"
        )
    if request.agent_id != agent.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent token cannot submit for another endpoint")

    # Validate telemetry type
    valid_types = ["process", "service", "startup", "eventlog"]
    if request.telemetry_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid telemetry type. Must be one of: {valid_types}"
        )

    # Decompress if needed
    batch = request.batch
    if request.compressed:
        try:
            import zstandard as zstd
            dctx = zstd.ZstdDecompressor()
            decompressed = dctx.decompress(batch)
            import json
            batch = json.loads(decompressed)
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="zstd not available for decompression"
            )

    # Insert telemetry records
    accepted = 0
    rejected = 0
    alerts_created = 0

    for record in batch:
        try:
            record["agent_id"] = request.agent_id
            record.setdefault("collected_at", datetime.now(timezone.utc))
            record.setdefault("sequence", request.sequence + accepted)
            for datetime_field in ("collected_at", "create_time", "event_timestamp"):
                value = record.get(datetime_field)
                if isinstance(value, str):
                    record[datetime_field] = datetime.fromisoformat(value.replace("Z", "+00:00"))

            if request.telemetry_type == "process":
                hashes = record.pop("hashes", None)
                if isinstance(hashes, dict):
                    record["exe_sha256"] = hashes.get("sha256")
                for collector_only_field in (
                    "memory_vms_bytes",
                    "signature", "collection_error", "is_complete",
                ):
                    record.pop(collector_only_field, None)
                # Preserve parent process fields for detection rules
                if "parent_name" not in record and "parent_process_name" in record:
                    record["parent_name"] = record.pop("parent_process_name")
                if "parent_exe" not in record and "parent_process_exe" in record:
                    record["parent_exe"] = record.pop("parent_process_exe")
                record = ProcessTelemetry(**record)
            elif request.telemetry_type == "service":
                account = record.pop("service_account", None)
                if account is not None:
                    record["account"] = account
                hashes = record.pop("hashes", None)
                if isinstance(hashes, dict):
                    record["exe_sha256"] = hashes.get("sha256")
                for collector_only_field in (
                    "load_order_group", "error_control",
                    "signature", "config_audit", "collection_error", "is_complete",
                ):
                    record.pop(collector_only_field, None)
                record = ServiceTelemetry(**record)
            elif request.telemetry_type == "startup":
                hashes = record.pop("hashes", None)
                if isinstance(hashes, dict):
                    record["exe_sha256"] = hashes.get("sha256")
                for collector_only_field in (
                    "source_key", "arguments", "user_sid", "run_as_admin",
                    "executable_path", "working_directory", "exe_md5",
                    "is_signed", "signer_name", "last_observed",
                    "registry_hive", "registry_key_path", "registry_value_type",
                    "task_triggers", "task_actions", "task_conditions",
                    "task_settings", "wmi_filter", "wmi_consumer",
                    "collection_error", "is_complete",
                ):
                    record.pop(collector_only_field, None)
                record = StartupInventory(**record)
            elif request.telemetry_type == "eventlog":
                record["source"] = record.pop("channel", record.get("source", "unknown"))
                extra_fields = (
                    "provider_name", "provider_guid", "level_value", "task",
                    "opcode", "keywords", "keywords_value", "user_sid",
                    "user_name", "user_domain", "process_id", "process_name",
                    "process_command_line", "parent_process_id",
                    "parent_process_name", "process_hash_sha256", "source_ip",
                    "destination_ip", "source_port", "destination_port",
                    "protocol", "file_path", "file_hash_sha256", "registry_key",
                    "registry_value", "registry_data", "service_name",
                    "service_display_name", "service_binary_path", "service_account",
                    "collection_error", "is_complete",
                )
                extracted = dict(record.get("extracted") or {})
                for field in extra_fields:
                    value = record.pop(field, None)
                    if value is not None:
                        extracted[field] = value
                record["extracted"] = extracted
                record = EventLogEntry(**record)

            db.add(record)
            accepted += 1
        except Exception as e:
            # Validation errors can include the rejected input value, such as a
            # command line containing a credential. Keep raw telemetry out of logs.
            logger.warning("telemetry_record_rejected", error_type=type(e).__name__)
            rejected += 1

    # Run detection engine on accepted records
    if accepted > 0:
        # Flush the session to ensure records are persisted before querying
        await db.flush()

        from ...detection_rules import DetectionEngine, ALL_RULES
        from ...models.alert import Alert, Evidence

        engine = DetectionEngine(ALL_RULES)

        # Re-fetch the accepted records to run detection.
        # Query by sequence range so the window is exact and not order-dependent.
        seq_start = request.sequence
        seq_end = request.sequence + accepted - 1

        if request.telemetry_type == "process":
            from ...models.telemetry import ProcessTelemetry
            stmt = (
                select(ProcessTelemetry)
                .where(
                    ProcessTelemetry.agent_id == request.agent_id,
                    ProcessTelemetry.sequence >= seq_start,
                    ProcessTelemetry.sequence <= seq_end,
                )
                .order_by(ProcessTelemetry.sequence.asc())
            )
            telemetry_records = (await db.execute(stmt)).scalars().all()
        elif request.telemetry_type == "service":
            from ...models.telemetry import ServiceTelemetry
            stmt = (
                select(ServiceTelemetry)
                .where(
                    ServiceTelemetry.agent_id == request.agent_id,
                    ServiceTelemetry.sequence >= seq_start,
                    ServiceTelemetry.sequence <= seq_end,
                )
                .order_by(ServiceTelemetry.sequence.asc())
            )
            telemetry_records = (await db.execute(stmt)).scalars().all()
        elif request.telemetry_type == "startup":
            from ...models.telemetry import StartupInventory
            stmt = (
                select(StartupInventory)
                .where(
                    StartupInventory.agent_id == request.agent_id,
                    StartupInventory.sequence >= seq_start,
                    StartupInventory.sequence <= seq_end,
                )
                .order_by(StartupInventory.sequence.asc())
            )
            telemetry_records = (await db.execute(stmt)).scalars().all()
        elif request.telemetry_type == "eventlog":
            from ...models.telemetry import EventLogEntry
            stmt = (
                select(EventLogEntry)
                .where(
                    EventLogEntry.agent_id == request.agent_id,
                    EventLogEntry.sequence >= seq_start,
                    EventLogEntry.sequence <= seq_end,
                )
                .order_by(EventLogEntry.sequence.asc())
            )
            telemetry_records = (await db.execute(stmt)).scalars().all()
        else:
            telemetry_records = []

        # Run detection on each record
        alerts_created = 0
        for record in telemetry_records:
            telemetry_dict = _record_to_telemetry_dict(record, request.telemetry_type)
            if not telemetry_dict:
                continue

            results = engine.evaluate(telemetry_dict)

            for result in results:
                rule = engine.rules.get(result.rule_id)

                if rule is None:
                    logger.warning(
                        "detection_rule_lookup_failed",
                        rule_id=result.rule_id,
                    )
                    continue

                now_utc = datetime.now(timezone.utc)

                # Stable dedup key that includes the entity (pid/name/sequence) so two
                # *different* processes triggering the same rule do NOT suppress each other.
                entity_id = telemetry_dict.get("process_pid") or telemetry_dict.get("service_name") or telemetry_dict.get("sequence") or str(id(record))
                dedup_key_raw = (
                    f"{result.rule_id}|{request.agent_id}|{entity_id}"
                )
                dedup_key_hash = hashlib.sha256(dedup_key_raw.encode()).hexdigest()[:16]

                # Correlation ID groups all alerts from the same batch/source event.
                correlation_id = hashlib.sha256(
                    f"{result.rule_id}|{request.agent_id}|{request.telemetry_type}|{request.sequence}".encode()
                ).hexdigest()[:16]

                # Detect already-seen entity-or-rule within the dedup window.
                existing_stmt = select(Alert).where(
                    Alert.dedup_key == dedup_key_hash,
                    Alert.agent_id == request.agent_id,
                    Alert.created_at >= now_utc - timedelta(seconds=rule.duplicate_window_seconds),
                )
                existing = (await db.execute(existing_stmt)).scalar_one_or_none()
                if existing:
                    # Duplicate — do NOT count as a new alert and do NOT create evidence.
                    logger.debug(
                        "suppressed_duplicate_alert",
                        rule_id=result.rule_id,
                        entity_id=entity_id,
                        existing_alert_id=existing.id,
                    )
                    continue

                # Deterministic alert ID from stable inputs; not dependent on wall-clock.
                alert_id = hashlib.sha256(
                    f"{dedup_key_raw}|{now_utc.isoformat(timespec='seconds')}|v1".encode()
                ).hexdigest()[:16]

                evidence_records = [telemetry_dict]
                size_bytes = sum(len(json.dumps(r, default=str).encode()) for r in evidence_records)

                alert = Alert(
                    id=alert_id,
                    agent_id=request.agent_id,
                    rule_id=result.rule_id,
                    rule_name=result.rule_name,
                    severity=result.severity,
                    status="new",
                    mitre_techniques=result.mitre_technique and [result.mitre_technique] or [],
                    mitre_tactics=rule.mitre_tactics or [],
                    correlation_key=correlation_id,
                    correlation_id=correlation_id,
                    finding_count=1,
                    summary=result.description,
                    description=result.description_details or result.description,
                    dedup_key=dedup_key_hash,
                    dedup_window_seconds=rule.duplicate_window_seconds,
                )
                db.add(alert)
                await db.flush()  # Obtain generated UUID (id) if not set deterministically

                evidence = Evidence(
                    id=str(uuid.uuid4()),
                    alert_id=alert.id,
                    telemetry_type=request.telemetry_type,
                    raw_records=evidence_records,
                    size_bytes=size_bytes,
                )
                db.add(evidence)
                alert.evidence_id = evidence.id
                await db.flush()

                alerts_created += 1

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise

    if accepted or alerts_created:
        publish_organization_update(agent.organization_id)

    return TelemetryBatchResponse(
        accepted=accepted,
        rejected=rejected,
        alerts_created=alerts_created,
        next_sequence=request.sequence + accepted,
    )


@router.post("/config/poll", response_model=ConfigPollResponse)
async def poll_config(
    request: ConfigPollRequest,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Agent configuration polling endpoint."""
    # Verify agent token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = authorization[7:]
    agent = await get_agent_from_token(db, token)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired agent token"
        )

    # Check if config update available
    current_version = request.current_config_version
    config_data, config_version = _effective_agent_config(agent)

    if current_version < config_version:
        return ConfigPollResponse(
            config_update_available=True,
            config=config_data,
            config_signature=_sign_config_for_agent(config_data, config_version),
            config_version=config_version,
        )

    return ConfigPollResponse(
        config_update_available=False,
        config_version=config_version,
    )


@router.get("/health", response_model=AgentHealthResponse)
async def get_agent_health(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(None),
):
    """Get agent health metrics."""
    # Verify agent token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = authorization[7:]
    agent = await get_agent_from_token(db, token)
    if not agent or agent.id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    health = agent.health_data or {}
    return AgentHealthResponse(
        cpu_percent=health.get("cpu_percent", 0),
        memory_mb=health.get("memory_mb", 0),
        memory_percent=health.get("memory_percent", 0),
        disk_free_gb=health.get("disk_free_gb", 0),
        disk_total_gb=health.get("disk_total_gb", 0),
        network_bytes_sent=health.get("network_bytes_sent", 0),
        network_bytes_recv=health.get("network_bytes_recv", 0),
        queue_depth=health.get("queue_depth", 0),
        batches_sent=health.get("batches_sent", 0),
        batches_failed=health.get("batches_failed", 0),
        events_sent=health.get("events_sent", 0),
        events_rejected=health.get("events_rejected", 0),
    )


@router.post("/re-enroll", response_model=ReEnrollmentResponse)
async def re_enroll_agent(
    request: ReEnrollmentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Handle agent re-enrollment (e.g., after VM copy, certificate expiry, etc.)."""
    enrollment, organization_id = await _resolve_enrollment_token(db, request.enrollment_token)

    # Find existing agent by machine_guid
    result = await db.execute(select(Agent).filter(Agent.machine_guid == request.machine_guid))
    existing = result.scalar_one_or_none()

    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No agent found with this machine GUID"
        )

    if existing.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No agent found with this enrollment token")

    # Verify the agent_id matches
    if existing.id != request.agent_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent ID mismatch: requested {request.agent_id}, found {existing.id}"
        )

    # Verify hostname consistency
    if existing.hostname != request.hostname:
        logger.warning(
            "hostname_changed_on_re_enroll",
            agent_id=existing.id,
            old_hostname=existing.hostname,
            new_hostname=request.hostname,
        )

    # Update agent info
    existing.hostname = request.hostname
    existing.os_version = request.os_version
    existing.agent_version = request.agent_version
    existing.last_seen = datetime.now(timezone.utc)
    existing.last_heartbeat = datetime.now(timezone.utc)
    existing.status = "online"
    existing.enrolled_at = datetime.now(timezone.utc)
    existing.credential_version += 1
    refresh_token = await _rotate_agent_refresh_token(db, existing)
    if enrollment:
        await _consume_enrollment_token(db, enrollment, existing.id)

    await db.commit()
    await db.refresh(existing)

    # Generate new token
    agent_token = _make_agent_access_token(existing)

    logger.info("agent_re_enrolled", agent_id=existing.id, hostname=request.hostname)

    config_data = get_config().agent_config
    return ReEnrollmentResponse(
        agent_id=existing.id,
        agent_token=agent_token,
        agent_refresh_token=refresh_token,
        client_certificate=None,
        ca_certificate=None,
        config=config_data.model_dump(),
        config_signature=_sign_config_for_agent(config_data, config_version),
        config_version=existing.config_version,
    )
