"""API routes for session metadata and permanent deletion."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.contracts import Session, SessionUpdateRequest
from app.api.mappers.sessions import to_api_session
from app.core.task_registry import is_active
from app.operations import session as session_operations
from app.storage import session_store

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
async def list_sessions() -> list[Session]:
    """Return persisted review sessions."""
    records = session_store.list_sessions()
    instruction_sets = session_store.get_instruction_set_references(
        [record.session_id for record in records]
    )
    return [
        to_api_session(
            record,
            analysis_active=is_active(record.session_id),
            instruction_set=instruction_sets.get(record.session_id),
        )
        for record in records
    ]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> Session:
    """Return session metadata."""
    record = session_store.require_session(session_id)
    instruction_set = session_store.get_instruction_set_references([session_id]).get(session_id)
    return to_api_session(
        record,
        analysis_active=is_active(session_id),
        instruction_set=instruction_set,
    )


@router.patch("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def request_update_session(session_id: str, request: SessionUpdateRequest) -> Response:
    """Update review session metadata."""
    session_store.require_session(session_id)
    if request.display_name is not None:
        session_operations.rename_session(session_id, request.display_name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def request_delete_session(session_id: str) -> Response:
    """Permanently purge a review session and its owned state."""
    session_operations.purge_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
