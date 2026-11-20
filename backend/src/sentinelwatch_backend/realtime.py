"""Small in-process tenant update hub used to invalidate dashboard snapshots.

Messages contain no telemetry or identifying data. Multi-worker deployments can
miss cross-worker notifications, so clients must retain their REST polling fallback.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class TenantUpdateHub:
    """Fan out bounded, tenant-scoped invalidation signals to active SSE clients."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[None]]] = defaultdict(set)

    def subscribe(self, organization_id: str) -> asyncio.Queue[None]:
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers[organization_id].add(queue)
        return queue

    def unsubscribe(self, organization_id: str, queue: asyncio.Queue[None]) -> None:
        subscribers = self._subscribers.get(organization_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(organization_id, None)

    def publish(self, organization_id: str) -> None:
        for queue in tuple(self._subscribers.get(organization_id, ())):
            if not queue.full():
                queue.put_nowait(None)


tenant_update_hub = TenantUpdateHub()


def publish_organization_update(organization_id: str) -> None:
    """Notify connected clients that their tenant's REST snapshots may have changed."""
    tenant_update_hub.publish(organization_id)
