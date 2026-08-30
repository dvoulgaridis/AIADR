"""API routes for Server-Sent Events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.operations.analyze.notifications import Subscription, register
from app.storage import session_store

router = APIRouter(tags=["events"])


async def _event_stream(subscription: Subscription) -> AsyncIterator[str]:
    try:
        async for event in subscription:
            yield f"event: {event.event_type}\ndata: {event.model_dump_json()}\n\n"
    finally:
        subscription.close()


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str) -> StreamingResponse:
    """Stream analysis progress events via SSE."""
    session_store.require_session(session_id)
    subscription = register(session_id)
    return StreamingResponse(
        _event_stream(subscription),
        media_type="text/event-stream",
        background=BackgroundTask(subscription.close),
    )
