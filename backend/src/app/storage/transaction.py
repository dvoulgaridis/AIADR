"""Minimal transaction boundary for primary writes and durable audit events."""

from __future__ import annotations

import sqlite3
from types import TracebackType
from typing import Literal

from app.audit.event_log import PersistedAuditEvent, append_events_with_connection
from app.audit.events import AuditEvent
from app.storage import db


def _rollback_preserving_error(
    connection: sqlite3.Connection,
    error: BaseException,
) -> None:
    try:
        connection.rollback()
    except BaseException as rollback_error:
        error.add_note(f"SQLite rollback also failed: {rollback_error!r}")


class Transaction:
    """Own one SQLite transaction and its pending audit events."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._events: list[AuditEvent] = []
        self.committed_events: tuple[PersistedAuditEvent, ...] = ()

    def __enter__(self) -> Transaction:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
        except BaseException:
            self.connection.close()
            raise
        return self

    def record(self, event: AuditEvent) -> None:
        """Queue an audit event for projection immediately before commit."""
        self._events.append(event)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc_type, traceback
        try:
            if exc is not None:
                _rollback_preserving_error(self.connection, exc)
                return False

            try:
                committed_events = tuple(
                    append_events_with_connection(
                        self.connection,
                        self._events,
                    )
                )
                self.connection.commit()
                self.committed_events = committed_events
            except BaseException as error:
                _rollback_preserving_error(self.connection, error)
                raise
            return False
        finally:
            self.connection.close()


def transaction() -> Transaction:
    """Create an unstarted transaction using a configured connection."""
    return Transaction(db.open_connection())
