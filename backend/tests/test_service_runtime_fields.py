from datetime import datetime, timezone

from sentinelwatch_backend.api.v1.telemetry import ServiceTelemetryResponse
from sentinelwatch_backend.models.telemetry import ServiceTelemetry


def test_service_runtime_metadata_is_persistable_and_returned():
    service = ServiceTelemetry(
        id="service-row",
        agent_id="agent-a",
        collected_at=datetime.now(timezone.utc),
        sequence=9,
        name="ExampleSvc",
        display_name="Example Service",
        description="Example service description",
        status="running",
        start_type="auto",
        pid=4312,
        binary_path=r"C:\\Program Files\\Example\\service.exe",
        service_type="own_process",
        dependencies=[],
        account="LocalSystem",
        exe_sha256=None,
    )

    response = ServiceTelemetryResponse.model_validate(service, from_attributes=True)

    assert "pid" in ServiceTelemetry.__table__.columns
    assert "description" in ServiceTelemetry.__table__.columns
    assert response.pid == 4312
    assert response.description == "Example service description"
