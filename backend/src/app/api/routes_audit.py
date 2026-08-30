"""API routes for audit history."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.contracts import AuditEventsResponse
from app.api.mappers.audit_events import to_api_audit_event
from app.audit.event_log import last_event_hash, list_events
from app.storage import session_store

router = APIRouter(tags=["audit"])


@router.get("/sessions/{session_id}/audit-events")
async def get_audit_events(session_id: str) -> AuditEventsResponse:
    """Return the append-only audit trail for a review session."""
    session_store.require_session(session_id)
    events = list_events(session_id)
    return AuditEventsResponse(
        session_id=session_id,
        event_count=len(events),
        last_event_hash=last_event_hash(session_id),
        events=[to_api_audit_event(event) for event in events],
    )
