"""Portable SQLite persistence for finalized export bundles."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.errors import ErrorCode, app_error
from app.files.records import StoredFile
from app.storage import db


@dataclass(frozen=True, slots=True)
class ExportRecord:
    """Persisted identity needed to resolve one export bundle."""

    export_id: str
    session_id: str
    filename: str
    stored_filename: str
    sha256: str


def insert_with_connection(
    connection: sqlite3.Connection,
    *,
    export_id: str,
    session_id: str,
    bundle: StoredFile,
) -> None:
    """Insert one finalized export using the caller's transaction."""
    connection.execute(
        """
        INSERT INTO exports (
            export_id, session_id, filename, stored_filename, sha256
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            export_id,
            session_id,
            bundle.filename,
            bundle.stored_filename,
            bundle.sha256,
        ),
    )


def get_latest(session_id: str) -> ExportRecord:
    """Return the latest persisted export for a session."""
    row = db.fetchone(
        """
        SELECT export_id, session_id, filename, stored_filename, sha256
        FROM exports
        WHERE session_id = ?
        ORDER BY created_at DESC, export_id DESC
        LIMIT 1
        """,
        (session_id,),
    )
    if row is None:
        raise app_error(ErrorCode.EXPORT_MISSING, details={"session_id": session_id})
    return ExportRecord(
        export_id=row["export_id"],
        session_id=row["session_id"],
        filename=row["filename"],
        stored_filename=row["stored_filename"],
        sha256=row["sha256"],
    )
