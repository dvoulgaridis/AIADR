"""Application workflows that mutate review sessions."""

from __future__ import annotations

from app.audit.events import ActorType, AuditEvent, AuditEventType
from app.core.task_registry import has_task
from app.errors import ErrorCode, app_error
from app.operations.analyze import notifications
from app.sessions.records import SessionRecord
from app.storage import session_store
from app.storage.file_store import purge_session_files
from app.storage.transaction import transaction


def rename_session(session_id: str, display_name: str) -> SessionRecord:
    """Rename a session and record the reviewer action atomically."""
    with transaction() as tx:
        session = session_store.rename_session_with_connection(
            tx.connection,
            session_id,
            display_name,
        )
        tx.record(
            AuditEvent(
                session_id=session_id,
                event_type=AuditEventType.SESSION_RENAMED,
                payload={"display_name_changed": True},
                actor_id="Reviewer-001",
                actor_type=ActorType.REVIEWER,
            )
        )
    return session


def purge_session(session_id: str) -> None:
    """Permanently remove one session and all state it owns."""
    if has_task(session_id):
        raise app_error(
            ErrorCode.ANALYSIS_ALREADY_RUNNING,
            details={"session_id": session_id},
        )

    with transaction() as tx:
        session_store.schedule_file_purge_with_connection(tx.connection, session_id)

    notifications.discard_session(session_id)
    purge_session_files(session_id)
    session_store.complete_file_purge(session_id)
