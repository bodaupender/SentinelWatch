"""Tenant update notifications are bounded and isolated between organizations."""

from sentinelwatch_backend.realtime import TenantUpdateHub


def test_update_hub_only_notifies_subscribers_in_the_matching_organization():
    hub = TenantUpdateHub()
    organization_a = hub.subscribe("organization-a")
    organization_b = hub.subscribe("organization-b")

    hub.publish("organization-a")

    assert organization_a.get_nowait() is None
    assert organization_b.empty()


def test_update_hub_coalesces_repeated_invalidations_and_unsubscribes():
    hub = TenantUpdateHub()
    queue = hub.subscribe("organization-a")

    hub.publish("organization-a")
    hub.publish("organization-a")

    assert queue.qsize() == 1
    hub.unsubscribe("organization-a", queue)
    hub.publish("organization-a")
    assert queue.qsize() == 1
