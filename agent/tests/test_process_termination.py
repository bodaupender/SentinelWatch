from datetime import datetime, timedelta, timezone

from sentinelwatch_agent.collectors.process import _create_termination_records
from sentinelwatch_agent.models import ProcessTelemetry


def _process(pid: int, created_at: datetime) -> ProcessTelemetry:
    return ProcessTelemetry(
        agent_id="agent-a",
        collected_at=created_at,
        sequence=1,
        pid=pid,
        ppid=4,
        name=f"process-{pid}.exe",
        create_time=created_at,
    )


def test_exited_process_gets_a_termination_record():
    created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    observed_at = datetime.now(timezone.utc)
    previous = {123: _process(123, created_at)}

    terminal = _create_termination_records(previous, [], set(), observed_at)

    assert len(terminal) == 1
    assert terminal[0].pid == 123
    assert terminal[0].create_time == created_at
    assert terminal[0].terminated_at == observed_at


def test_pid_reuse_terminates_prior_process_identity():
    old_created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    new_created_at = datetime.now(timezone.utc)
    previous = {123: _process(123, old_created_at)}

    terminal = _create_termination_records(
        previous,
        [_process(123, new_created_at)],
        {123},
        new_created_at,
    )

    assert len(terminal) == 1
    assert terminal[0].create_time == old_created_at
    assert terminal[0].terminated_at == new_created_at


def test_active_process_identity_does_not_get_a_termination_record():
    created_at = datetime.now(timezone.utc)
    process = _process(123, created_at)

    terminal = _create_termination_records({123: process}, [process], {123}, created_at)

    assert terminal == []
