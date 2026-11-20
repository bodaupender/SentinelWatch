"""Exercise tenant scoping through the real telemetry API queries."""

from datetime import datetime, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from sentinelwatch_backend.api.deps import get_current_analyst, get_current_organization
from sentinelwatch_backend.database import get_db
from sentinelwatch_backend.main import create_app
from sentinelwatch_backend.models import (
    Agent,
    Organization,
    OrganizationRole,
    OrganizationMembership,
    ProcessTelemetry,
    ServiceTelemetry,
    User,
)
from sentinelwatch_backend.models.agent import AgentStatus
from sentinelwatch_backend.models.user import UserRole, UserStatus


@pytest.mark.asyncio
async def test_process_and_service_inventory_never_returns_another_tenant(
    test_config, db_session
):
    now = datetime.now(timezone.utc)
    org_a = Organization(id="org-a", name="Org A", slug="org-a")
    org_b = Organization(id="org-b", name="Org B", slug="org-b")
    viewer = User(
        id="user-a",
        username="viewer-a",
        email="viewer-a@example.test",
        password_hash="not-used-in-this-dependency-overridden-test",
        role=UserRole.ANALYST,
        status=UserStatus.ACTIVE,
    )
    agent_a = Agent(
        id="agent-a", organization_id=org_a.id, hostname="endpoint-a",
        machine_guid="machine-a", os_version="Windows 11", agent_version="test",
        status=AgentStatus.ONLINE,
    )
    agent_b = Agent(
        id="agent-b", organization_id=org_b.id, hostname="endpoint-b",
        machine_guid="machine-b", os_version="Windows 11", agent_version="test",
        status=AgentStatus.ONLINE,
    )
    db_session.add_all([
        org_a,
        org_b,
        viewer,
        OrganizationMembership(
            id="membership-a", organization_id=org_a.id,
            user_id=viewer.id, role=OrganizationRole.ANALYST,
        ),
        agent_a,
        agent_b,
        ProcessTelemetry(
            id="process-a", agent_id=agent_a.id, collected_at=now, sequence=1,
            pid=100, ppid=1, name="process-a.exe", create_time=now,
        ),
        ProcessTelemetry(
            id="process-b", agent_id=agent_b.id, collected_at=now, sequence=1,
            pid=200, ppid=1, name="process-b.exe", create_time=now,
        ),
        ServiceTelemetry(
            id="service-a", agent_id=agent_a.id, collected_at=now, sequence=1,
            name="service-a", status="running", start_type="auto",
        ),
        ServiceTelemetry(
            id="service-b", agent_id=agent_b.id, collected_at=now, sequence=1,
            name="service-b", status="running", start_type="auto",
        ),
    ])
    await db_session.commit()

    app = create_app(test_config)

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_analyst] = lambda: viewer
    app.dependency_overrides[get_current_organization] = lambda: org_a

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for endpoint, expected_name in (
                ("processes", "process-a.exe"),
                ("services", "service-a"),
            ):
                response = await client.get(f"/api/v1/telemetry/{endpoint}?limit=100")
                assert response.status_code == 200
                payload = response.json()
                assert payload["total"] == 1
                assert [item["name"] for item in payload["data"]] == [expected_name]

                # A caller-supplied foreign agent ID must not bypass the tenant filter.
                foreign_response = await client.get(
                    f"/api/v1/telemetry/{endpoint}?agent_id=agent-b&limit=100"
                )
                assert foreign_response.status_code == 200
                assert foreign_response.json()["total"] == 0
                assert foreign_response.json()["data"] == []
    finally:
        app.dependency_overrides.clear()
