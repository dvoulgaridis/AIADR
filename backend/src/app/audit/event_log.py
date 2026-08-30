"""Append-only hash-chained audit events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from typing import TypedDict, cast

from pydantic import JsonValue

from app.audit.events import ActorType, AuditEvent, AuditEventType
from app.core.ids import new_event_id
from app.storage import db


class _AuditEventEnvelope(TypedDict):
    event_id: str
    session_id: str
    actor_id: str
    actor_type: ActorType
    event_type: AuditEventType
    payload: dict[str, JsonValue]
    previous_hash: str | None
    created_at: str


class PersistedAuditEvent(_AuditEventEnvelope):
    """JSON-compatible audit event after storage assigns its hash-chain fields."""

    event_hash: str


def _canonical_json(data: JsonValue | _AuditEventEnvelope) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _hash_event(event: _AuditEventEnvelope) -> str:
    return hashlib.sha256(_canonical_json(event).encode("utf-8")).hexdigest()


def _last_hash_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT event_hash FROM audit_events
        WHERE session_id = ?
        ORDER BY rowid DESC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    return row["event_hash"] if row is not None else None


def _append_event_after(
    connection: sqlite3.Connection,
    event: AuditEvent,
    previous_hash: str | None,
) -> PersistedAuditEvent:
    created_at = event.occurred_at.isoformat()
    event_id = new_event_id()
    stored_event: _AuditEventEnvelope = {
        "event_id": event_id,
        "session_id": event.session_id,
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "event_type": event.event_type,
        "payload": event.payload,
        "previous_hash": previous_hash,
        "created_at": created_at,
    }
    event_hash = _hash_event(stored_event)
    connection.execute(
        """
        INSERT INTO audit_events (
            event_id, session_id, actor_id, actor_type, event_type, payload,
            previous_hash, event_hash, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event.session_id,
            event.actor_id,
            event.actor_type,
            event.event_type,
            _canonical_json(event.payload),
            previous_hash,
            event_hash,
            created_at,
        ),
    )
    persisted_event: PersistedAuditEvent = {
        **stored_event,
        "event_hash": event_hash,
    }
    return persisted_event


def append_event_with_connection(
    connection: sqlite3.Connection,
    event: AuditEvent,
) -> PersistedAuditEvent:
    """Append one audit event using the caller's transaction."""
    previous_hash = _last_hash_with_connection(connection, event.session_id)
    return _append_event_after(connection, event, previous_hash)


def append_events_with_connection(
    connection: sqlite3.Connection,
    events: Iterable[AuditEvent],
) -> list[PersistedAuditEvent]:
    """Append audit events in order using the caller's transaction."""
    previous_hashes: dict[str, str | None] = {}
    persisted_events: list[PersistedAuditEvent] = []

    for event in events:
        if event.session_id not in previous_hashes:
            previous_hashes[event.session_id] = _last_hash_with_connection(
                connection,
                event.session_id,
            )

        persisted_event = _append_event_after(
            connection,
            event,
            previous_hashes[event.session_id],
        )
        previous_hashes[event.session_id] = persisted_event["event_hash"]
        persisted_events.append(persisted_event)

    return persisted_events


def _decode_events(rows: Iterable[sqlite3.Row]) -> list[PersistedAuditEvent]:
    return [
        {
            "event_id": row["event_id"],
            "session_id": row["session_id"],
            "actor_id": row["actor_id"],
            "actor_type": ActorType(str(row["actor_type"])),
            "event_type": AuditEventType(str(row["event_type"])),
            "payload": cast(dict[str, JsonValue], json.loads(row["payload"])),
            "previous_hash": row["previous_hash"],
            "event_hash": row["event_hash"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_events(session_id: str) -> list[PersistedAuditEvent]:
    """Return audit events in append order."""
    rows = db.fetchall(
        """
        SELECT * FROM audit_events
        WHERE session_id = ?
        ORDER BY rowid ASC
        """,
        (session_id,),
    )
    return _decode_events(rows)


def list_events_through(
    session_id: str,
    boundary_hash: str,
) -> list[PersistedAuditEvent]:
    """Return the audit prefix ending at a persisted event hash."""
    boundary = db.fetchone(
        """
        SELECT rowid FROM audit_events
        WHERE session_id = ? AND event_hash = ?
        """,
        (session_id, boundary_hash),
    )
    if boundary is None:
        raise ValueError("Audit boundary does not belong to the session.")

    rows = db.fetchall(
        """
        SELECT * FROM audit_events
        WHERE session_id = ? AND rowid <= ?
        ORDER BY rowid ASC
        """,
        (session_id, boundary["rowid"]),
    )
    return _decode_events(rows)


def last_event_hash(session_id: str) -> str | None:
    """Return the latest audit event hash for a session."""
    row = db.fetchone(
        """
        SELECT event_hash FROM audit_events
        WHERE session_id = ?
        ORDER BY rowid DESC
        LIMIT 1
        """,
        (session_id,),
    )
    return row["event_hash"] if row is not None else None
