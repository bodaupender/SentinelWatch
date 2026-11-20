from datetime import datetime, timezone

from sentinelwatch_backend.api.v1.telemetry import ProcessTelemetryResponse
from sentinelwatch_backend.models.telemetry import ProcessTelemetry


def test_process_runtime_fields_are_persistable_and_returned():
    process = ProcessTelemetry(
        id="process-row",
        agent_id="agent-a",
        collected_at=datetime.now(timezone.utc),
        sequence=9,
        pid=4312,
        ppid=4,
        name="example.exe",
        status="running",
        num_threads=8,
        num_handles=42,
    )

    response = ProcessTelemetryResponse.model_validate(process, from_attributes=True)

    assert {"status", "num_threads", "num_handles"}.issubset(ProcessTelemetry.__table__.columns.keys())
    assert response.status == "running"
    assert response.num_threads == 8
    assert response.num_handles == 42
