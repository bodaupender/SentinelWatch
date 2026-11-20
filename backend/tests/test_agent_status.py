"""Agent presence reporting distinguishes metadata-only entries from enrolled agents."""

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from sentinelwatch_backend.api.v1.agents import _reported_status


def test_metadata_only_agent_is_unregistered_until_it_checks_in():
    agent = SimpleNamespace(last_heartbeat=None, last_seen=None, status="unregistered")
    assert _reported_status(agent) == "unregistered"


def test_agent_status_uses_heartbeat_freshness():
    now = datetime.now(timezone.utc)
    agent = SimpleNamespace(last_heartbeat=now, last_seen=None, status="online")
    assert _reported_status(agent) == "online"

    agent.last_heartbeat = now - timedelta(minutes=5)
    assert _reported_status(agent) == "stale"

    agent.last_heartbeat = now - timedelta(minutes=20)
    assert _reported_status(agent) == "offline"
