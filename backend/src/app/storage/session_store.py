"""SQLite-backed session state and hydration."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.errors import ErrorCode, app_error
from app.files.records import StoredFile
from app.sessions.records import (
    InstructionSetLockRecord,
    InstructionSetReferenceRecord,
    SessionRecord,
    SessionStatus,
)
from app.sources.records import SourceRecord
from app.storage import db, session_file_store


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_row_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
) -> Any:
    row = connection.execute(
        "SELECT * FROM sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        raise app_error(
            ErrorCode.SESSION_NOT_FOUND,
            details={"session_id": session_id},
        )
    return row


def _hydrate_session(
    row: Any,
    source: SourceRecord,
    rendered_file: StoredFile | None,
) -> SessionRecord:
    return SessionRecord(
        session_id=row["session_id"],
        source=source,
        status=SessionStatus(str(row["status"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        display_name=row["display_name"],
        rendered_file=rendered_file,
        error_message=row["error_message"],
    )


def _hydrate_rows(
    connection: sqlite3.Connection,
    rows: list[Any],
) -> list[SessionRecord]:
    session_ids = [str(row["session_id"]) for row in rows]
    relations = session_file_store.get_relations_with_connection(connection, session_ids)
    return [_hydrate_session(row, *relations[str(row["session_id"])]) for row in rows]


def display_name_for_filename(filename: str) -> str:
    """Return a default review title from a filename."""
    stem = Path(filename).stem.strip()
    return stem or Path(filename).name.strip() or "Untitled review"


def put_session_with_connection(connection: sqlite3.Connection, session: SessionRecord) -> None:
    """Insert a complete session and its source in the caller's transaction."""
    display_name = session.display_name or display_name_for_filename(session.source.file.filename)
    connection.execute(
        """
        INSERT INTO sessions (
            session_id, status, created_at, updated_at, display_name, error_message
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            session.session_id,
            session.status,
            session.created_at,
            session.updated_at or session.created_at,
            display_name,
            session.error_message,
        ),
    )
    session_file_store.put_source_with_connection(
        connection,
        session.session_id,
        session.source,
    )


def get_session(session_id: str) -> SessionRecord | None:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return _hydrate_rows(connection, [row])[0]


def require_session(session_id: str) -> SessionRecord:
    session = get_session(session_id)
    if session is None:
        raise app_error(ErrorCode.SESSION_NOT_FOUND, details={"session_id": session_id})
    return session


def update_session_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    **updates: object,
) -> SessionRecord:
    """Patch mutable session state using the caller's transaction."""
    current = _require_row_with_connection(connection, session_id)
    allowed = {"status", "updated_at", "display_name", "error_message"}
    invalid = set(updates) - allowed
    if invalid:
        raise ValueError(f"Unsupported session field(s): {', '.join(sorted(invalid))}")
    if updates:
        patch = dict(updates)
        patch["updated_at"] = patch.get("updated_at") or _now()
        assignments = ", ".join(f"{key} = ?" for key in patch)
        connection.execute(
            f"UPDATE sessions SET {assignments} WHERE session_id = ?",
            (*patch.values(), session_id),
        )
        current = _require_row_with_connection(connection, session_id)
    return _hydrate_rows(connection, [current])[0]


def replace_source_metadata_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    source: SourceRecord,
) -> SessionRecord:
    """Replace validated derived source measurements."""
    _require_row_with_connection(connection, session_id)
    session_file_store.replace_source_metadata_with_connection(
        connection,
        session_id,
        source,
    )
    return update_session_with_connection(connection, session_id)


def rename_session_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    display_name: str,
) -> SessionRecord:
    """Rename a user-visible review entry using the caller's transaction."""
    normalized = display_name.strip()
    if not normalized:
        current = update_session_with_connection(connection, session_id)
        normalized = display_name_for_filename(current.source.file.filename)
    return update_session_with_connection(
        connection,
        session_id,
        display_name=normalized,
    )


def schedule_file_purge_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
) -> None:
    """Delete a session while durably retaining its pending file cleanup."""
    _require_row_with_connection(connection, session_id)
    connection.execute(
        "INSERT INTO pending_session_file_purges (session_id) VALUES (?)",
        (session_id,),
    )
    cursor = connection.execute(
        "DELETE FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("The session could not be scheduled for permanent deletion.")


def list_pending_file_purges() -> list[str]:
    """Return session IDs whose managed files still require deletion."""
    rows = db.fetchall(
        "SELECT session_id FROM pending_session_file_purges ORDER BY created_at, session_id"
    )
    return [str(row["session_id"]) for row in rows]


def complete_file_purge(session_id: str) -> None:
    """Remove a completed file-purge instruction idempotently."""
    db.execute(
        "DELETE FROM pending_session_file_purges WHERE session_id = ?",
        (session_id,),
    )


def list_sessions() -> list[SessionRecord]:
    with db.connect() as connection:
        rows = list(
            connection.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC, created_at DESC"
            ).fetchall()
        )
        return _hydrate_rows(connection, rows)


def _row_to_instruction_set_lock(row: Any) -> InstructionSetLockRecord:
    return InstructionSetLockRecord(
        session_id=row["session_id"],
        instruction_set_id=row["instruction_set_id"],
        instruction_set_content_hash=row["instruction_set_content_hash"],
        snapshot_bytes=row["snapshot_bytes"],
        created_at=row["created_at"],
    )


def get_instruction_set_lock(session_id: str) -> InstructionSetLockRecord | None:
    row = db.fetchone(
        "SELECT * FROM session_instruction_sets WHERE session_id = ?",
        (session_id,),
    )
    return _row_to_instruction_set_lock(row) if row is not None else None


def get_instruction_set_references(
    session_ids: list[str],
) -> dict[str, InstructionSetReferenceRecord]:
    """Return snapshot identities for the requested sessions without BLOBs."""
    if not session_ids:
        return {}
    placeholders = ", ".join("?" for _ in session_ids)
    with db.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT session_id, instruction_set_id, instruction_set_content_hash
            FROM session_instruction_sets
            WHERE session_id IN ({placeholders})
            """,
            tuple(session_ids),
        ).fetchall()
    references = {
        str(row["session_id"]): InstructionSetReferenceRecord(
            instruction_set_id=row["instruction_set_id"],
            instruction_set_content_hash=row["instruction_set_content_hash"],
        )
        for row in rows
    }
    return references


def replace_instruction_set_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    *,
    instruction_set_id: str,
    instruction_set_content_hash: str,
    snapshot_bytes: bytes,
) -> InstructionSetLockRecord:
    """Replace the session's policy snapshot during successful analysis."""
    _require_row_with_connection(connection, session_id)
    connection.execute(
        """
        INSERT INTO session_instruction_sets (
            session_id, instruction_set_id, instruction_set_content_hash, snapshot_bytes
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            instruction_set_id = excluded.instruction_set_id,
            instruction_set_content_hash = excluded.instruction_set_content_hash,
            snapshot_bytes = excluded.snapshot_bytes,
            created_at = CURRENT_TIMESTAMP
        """,
        (
            session_id,
            instruction_set_id,
            instruction_set_content_hash,
            snapshot_bytes,
        ),
    )
    row = connection.execute(
        "SELECT * FROM session_instruction_sets WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    assert row is not None
    return _row_to_instruction_set_lock(row)
