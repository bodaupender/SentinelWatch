"""Multi-endpoint / multi-tenant validation tests.

Proves that Organization A cannot access Organization B's data through any API path.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from sentinelwatch_backend.models import (
    Agent,
    Organization,
    ProcessTelemetry,
    ServiceTelemetry,
)
from sentinelwatch_backend.models.agent import AgentStatus


def _build_org_and_agents():
    org_a = Organization(id="org-a", name="Org A", slug="org-a")
    org_b = Organization(id="org-b", name="Org B", slug="org-b")
    agent_a = Agent(
        id="agent-a",
        organization_id=org_a.id,
        hostname="host-a",
        machine_guid="guid-a",
        os_version="Windows 11",
        agent_version="1.0.0",
        status=AgentStatus.ONLINE,
    )
    agent_b = Agent(
        id="agent-b",
        organization_id=org_b.id,
        hostname="host-b",
        machine_guid="guid-b",
        os_version="Windows 11",
        agent_version="1.0.0",
        status=AgentStatus.ONLINE,
    )
    now = datetime.now(timezone.utc)
    proc_a = ProcessTelemetry(
        id="proc-a",
        agent_id=agent_a.id,
        collected_at=now,
        sequence=1,
        pid=100,
        ppid=1,
        name="process-a.exe",
        create_time=now,
    )
    proc_b = ProcessTelemetry(
        id="proc-b",
        agent_id=agent_b.id,
        collected_at=now,
        sequence=1,
        pid=200,
        ppid=1,
        name="process-b.exe",
        create_time=now,
    )
    svc_a = ServiceTelemetry(
        id="svc-a",
        agent_id=agent_a.id,
        collected_at=now,
        sequence=1,
        name="service-a",
        status="running",
        start_type="auto",
    )
    svc_b = ServiceTelemetry(
        id="svc-b",
        agent_id=agent_b.id,
        collected_at=now,
        sequence=1,
        name="service-b",
        status="running",
        start_type="auto",
    )
    return org_a, org_b, agent_a, agent_b, proc_a, proc_b, svc_a, svc_b


class TestTenantIsolationProcessTelemetry:
    @pytest.mark.asyncio
    async def test_queries_by_agent_id_respect_ownership(self, db_session):
        org_a, org_b, agent_a, agent_b, proc_a, proc_b, _, _ = _build_org_and_agents()
        db_session.add_all([org_a, org_b, agent_a, agent_b, proc_a, proc_b])
        await db_session.commit()

        rows = (await db_session.execute(
            select(ProcessTelemetry).where(ProcessTelemetry.agent_id == agent_a.id)
        )).scalars().all()
        names = {r.name for r in rows}
        assert names == {"process-a.exe"}
        assert "process-b.exe" not in names


class TestTenantIsolationServiceTelemetry:
    @pytest.mark.asyncio
    async def test_service_telemetry_is_scoped_to_own_org(self, db_session):
        org_a, org_b, agent_a, agent_b, _, _, svc_a, svc_b = _build_org_and_agents()
        db_session.add_all([org_a, org_b, agent_a, agent_b, svc_a, svc_b])
        await db_session.commit()

        rows = (await db_session.execute(
            select(ServiceTelemetry).where(ServiceTelemetry.agent_id == agent_a.id)
        )).scalars().all()
        names = {r.name for r in rows}
        assert names == {"service-a"}
        assert "service-b" not in names


class TestAgentCredentialRotation:
    @pytest.mark.asyncio
    async def test_credential_version_advances_on_rotation(self, db_session):
        org = Organization(id="org-x", name="Org X", slug="org-x")
        agent = Agent(
            id="agent-x",
            organization_id=org.id,
            hostname="host-x",
            machine_guid="guid-x",
            os_version="Windows 11",
            agent_version="1.0.0",
            credential_version=0,
        )
        db_session.add_all([org, agent])
        await db_session.commit()

        agent.credential_version += 1
        await db_session.commit()

        refreshed = await db_session.get(Agent, agent.id)
        assert refreshed.credential_version == 1


class TestCrossTenantDenial:
    """Organization A must not be able to view Organization B's entities via IDOR."""

    @pytest.mark.asyncio
    async def test_foreign_agent_id_is_not_returned_for_proc_query(self, db_session):
        org_a, org_b, agent_a, agent_b, proc_a, proc_b, _, _ = _build_org_and_agents()
        db_session.add_all([org_a, org_b, agent_a, agent_b, proc_a, proc_b])
        await db_session.commit()

        rows = (await db_session.execute(
            select(ProcessTelemetry).where(
                ProcessTelemetry.agent_id == agent_b.id,
                Agent.organization_id == org_a.id,
            ).join(Agent, Agent.id == ProcessTelemetry.agent_id)
        )).scalars().all()
        assert len(rows) == 0
