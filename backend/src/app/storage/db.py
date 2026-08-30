"""SQLite persistence helpers for AIADR runtime state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from app.core.paths import db_path

APPLICATION_ID = 0x41494144
SCHEMA_VERSION = 1
_BUSY_TIMEOUT_MS = 5_000


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")


def _connect_path(path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    _configure_connection(connection)
    return connection


def open_connection() -> sqlite3.Connection:
    """Open and configure one SQLite connection."""
    path = db_path()
    if not path.is_file():
        raise RuntimeError("The AIADR database has not been initialized.")
    return _connect_path(path)


@contextmanager
def connect(immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a configured SQLite connection and manage its transaction."""
    connection = open_connection()
    try:
        if immediate:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def database_exists() -> bool:
    """Return whether the configured SQLite database file exists."""
    return db_path().is_file()


def _compatibility_error(reason: str) -> RuntimeError:
    return RuntimeError(
        f"The AIADR database is incompatible: {reason}. "
        "No database or managed files were modified. Back up or remove the "
        "configured data directory before starting fresh."
    )


def validate_database() -> None:
    """Validate an existing database without modifying it."""
    path = db_path()
    try:
        connection = _connect_path(path, read_only=True)
        try:
            application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
            schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        finally:
            connection.close()
    except (OSError, sqlite3.DatabaseError) as exc:
        raise _compatibility_error("the file is not a readable AIADR database") from exc

    if application_id != APPLICATION_ID:
        raise _compatibility_error("the application identifier does not match AIADR")
    if schema_version != SCHEMA_VERSION:
        raise _compatibility_error(
            f"schema version {schema_version} does not match required version {SCHEMA_VERSION}"
        )


def enable_wal() -> None:
    """Enable and verify write-ahead logging for a validated database."""
    connection = open_connection()
    try:
        row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        journal_mode = str(row[0]).lower() if row is not None else ""
        if journal_mode != "wal":
            raise RuntimeError("SQLite WAL mode could not be enabled for the AIADR database.")
    finally:
        connection.close()


def initialize_database() -> None:
    """Create a new AIADR database and stamp its compatibility metadata."""
    path = db_path()
    if path.exists():
        raise RuntimeError("Refusing to initialize over an existing database path.")
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect_path(path)
    try:
        row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
        journal_mode = str(row[0]).lower() if row is not None else ""
        if journal_mode != "wal":
            raise RuntimeError("SQLite WAL mode could not be enabled for the AIADR database.")
        connection.executescript(
            """
            BEGIN IMMEDIATE;

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'uploaded',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                display_name TEXT,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS pending_session_file_purges (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS session_files (
                session_id TEXT NOT NULL
                    REFERENCES sessions(session_id) ON DELETE CASCADE,
                role TEXT NOT NULL
                    CHECK (role IN ('source', 'rendered')),
                kind TEXT NOT NULL,
                format TEXT NOT NULL,
                filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                line_count INTEGER,
                character_count INTEGER,
                page_count INTEGER,
                width INTEGER,
                height INTEGER,
                duration_seconds REAL,
                sample_rate INTEGER,
                block_count INTEGER,
                targetable_image_count INTEGER,
                unsupported_image_count INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, role)
            );

            CREATE TABLE IF NOT EXISTS findings (
                finding_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                detected_entity_type TEXT,
                reviewed_entity_type TEXT,
                privacy_category TEXT NOT NULL DEFAULT 'unknown',
                special_category_type TEXT NOT NULL DEFAULT 'none',
                data_subject_context TEXT NOT NULL DEFAULT 'unknown',
                label TEXT NOT NULL DEFAULT '',
                detection_confidence REAL,
                privacy_risk TEXT NOT NULL DEFAULT 'medium',
                target_json TEXT NOT NULL,
                description TEXT,
                reason TEXT,
                origin TEXT NOT NULL DEFAULT 'model',
                created_by TEXT,
                review_decision TEXT NOT NULL DEFAULT 'needs_review',
                edited INTEGER NOT NULL DEFAULT 0,
                reviewer_note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS layers (
                layer_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                finding_id TEXT NOT NULL UNIQUE REFERENCES findings(finding_id) ON DELETE CASCADE,
                action TEXT NOT NULL DEFAULT 'redact',
                effect TEXT NOT NULL DEFAULT 'box',
                effect_source TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                fill_color TEXT NOT NULL DEFAULT '#000000',
                custom_text TEXT,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pdf_text_lines (
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                page INTEGER NOT NULL,
                line_id TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, page, line_id)
            );

            CREATE TABLE IF NOT EXISTS docx_text_blocks (
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                block_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                story_kind TEXT NOT NULL,
                part_uri TEXT NOT NULL,
                structural_path TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, block_id),
                UNIQUE (session_id, ordinal)
            );

            CREATE TABLE IF NOT EXISTS docx_image_occurrences (
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                occurrence_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                story_kind TEXT NOT NULL,
                part_uri TEXT NOT NULL,
                media_type TEXT NOT NULL,
                asset_filename TEXT,
                normalized_sha256 TEXT,
                width_px INTEGER,
                height_px INTEGER,
                targetable INTEGER NOT NULL,
                unsupported_reason TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, occurrence_id),
                UNIQUE (session_id, ordinal)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                actor_id TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                previous_hash TEXT,
                event_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS model_logs (
                log_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'started',
                completed_at TEXT,
                duration_ms INTEGER,
                kind TEXT NOT NULL,
                page INTEGER,
                api_format TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT '',
                request_summary TEXT NOT NULL,
                result_summary TEXT NOT NULL,
                debug_request_payload TEXT,
                debug_response_content TEXT,
                debug_error_message TEXT,
                finish_reason TEXT,
                input_count_method TEXT,
                estimated_input_tokens INTEGER,
                provider_counted_input_tokens INTEGER,
                requested_output_tokens INTEGER,
                max_input_tokens INTEGER,
                actual_input_tokens INTEGER,
                actual_output_tokens INTEGER,
                total_tokens INTEGER,
                reasoning_tokens INTEGER
            );

            CREATE TABLE IF NOT EXISTS exports (
                export_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS session_instruction_sets (
                session_id TEXT PRIMARY KEY
                    REFERENCES sessions(session_id) ON DELETE CASCADE,
                instruction_set_id TEXT NOT NULL,
                instruction_set_content_hash TEXT NOT NULL,
                snapshot_bytes BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
            f"""
            PRAGMA application_id = {APPLICATION_ID};
            PRAGMA user_version = {SCHEMA_VERSION};
            COMMIT;
            """
        )
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def execute(sql: str, parameters: Iterable[Any] = ()) -> None:
    """Execute a write statement."""
    with connect() as connection:
        connection.execute(sql, tuple(parameters))


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    """Execute a write statement for many rows."""
    with connect() as connection:
        connection.executemany(sql, [tuple(row) for row in rows])


def fetchone(sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Row | None:
    """Fetch one row."""
    with connect() as connection:
        return cast(sqlite3.Row | None, connection.execute(sql, tuple(parameters)).fetchone())


def fetchall(sql: str, parameters: Iterable[Any] = ()) -> list[sqlite3.Row]:
    """Fetch all rows."""
    with connect() as connection:
        return list(connection.execute(sql, tuple(parameters)).fetchall())
