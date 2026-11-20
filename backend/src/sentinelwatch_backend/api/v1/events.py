"""Authenticated, tenant-scoped Server-Sent Events for dashboard refreshes."""

import asyncio
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from ...config import get_config
from ...database import get_session_factory
from ...models import Organization, User
from ...realtime import tenant_update_hub
from ..deps import get_current_analyst, get_current_organization, get_current_user

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream_updates(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    selected_organization_id: Optional[str] = Header(None, alias="X-Organization-ID"),
):
    """Stream generic invalidation signals without holding a database session open."""
    if not get_config().features.websocket_updates:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Live updates are disabled")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[7:]
    async with get_session_factory()() as db:
        user: User = await get_current_user(token, db)
        organization: Organization = await get_current_organization(
            selected_organization_id, user, db
        )
        await get_current_analyst(user, organization, db)
        organization_id = organization.id

    async def event_stream():
        queue = tenant_update_hub.subscribe(organization_id)
        try:
            # Re-fetch the initial REST snapshots on connect/reconnect so no
            # transient update is required to bring the dashboard up to date.
            yield "event: ready\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    await asyncio.wait_for(queue.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                yield "event: invalidate\ndata: {}\n\n"
        finally:
            tenant_update_hub.unsubscribe(organization_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
