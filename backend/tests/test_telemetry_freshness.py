from datetime import datetime, timedelta, timezone

from sentinelwatch_backend.api.v1.telemetry import _classify_snapshot_freshness


def test_stale_agent_snapshots_are_excluded_from_current_inventory():
    now = datetime.now(timezone.utc)
    snapshots = [
        ("fresh-agent", now - timedelta(seconds=90)),
        ("stale-agent", now - timedelta(seconds=181)),
    ]

    reporting, newest, stale_count = _classify_snapshot_freshness(snapshots, now)

    assert reporting == [("fresh-agent", snapshots[0][1])]
    assert newest == snapshots[0][1]
    assert stale_count == 1


def test_naive_database_timestamps_are_treated_as_utc():
    now = datetime.now(timezone.utc)
    naive = (now - timedelta(seconds=30)).replace(tzinfo=None)

    reporting, newest, stale_count = _classify_snapshot_freshness([("agent", naive)], now)

    assert reporting == [("agent", naive.replace(tzinfo=timezone.utc))]
    assert newest == naive.replace(tzinfo=timezone.utc)
    assert stale_count == 0
