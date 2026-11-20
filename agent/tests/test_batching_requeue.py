"""Bounded retry buffering for failed telemetry uploads."""

from types import SimpleNamespace

from sentinelwatch_agent.transport.batching import BatcherConfig, TelemetryBatcher


def complete_without_wait(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    raise AssertionError("The batcher unit path unexpectedly waited for external I/O")


def _records(*sequences):
    return [SimpleNamespace(sequence=number, agent_id="agent-a") for number in sequences]


def test_failed_batch_is_requeued_before_newer_buffered_records():
    batcher = TelemetryBatcher(
        "process", "agent-a", config=BatcherConfig(max_pending_records=8), auto_flush=False
    )
    batcher._buffer = _records(4, 5)

    dropped = complete_without_wait(batcher.requeue(_records(1, 2, 3)))

    assert dropped == 0
    assert [record.sequence for record in batcher._buffer] == [1, 2, 3, 4, 5]
    assert batcher._sequence == 5


def test_retry_buffer_discards_oldest_records_when_capacity_is_reached():
    batcher = TelemetryBatcher(
        "process", "agent-a", config=BatcherConfig(max_pending_records=4), auto_flush=False
    )
    batcher._buffer = _records(4, 5)

    dropped = complete_without_wait(batcher.requeue(_records(1, 2, 3)))

    assert dropped == 1
    assert [record.sequence for record in batcher._buffer] == [2, 3, 4, 5]
