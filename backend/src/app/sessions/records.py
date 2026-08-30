"""Persistence-facing session record used inside the backend."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.files.records import StoredFile
from app.sources.records import SourceRecord


class SessionStatus(StrEnum):
    UPLOADED = "uploaded"
    REVIEW_READY = "review_ready"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Complete internal session state, including storage-only fields."""

    session_id: str
    source: SourceRecord
    created_at: str
    status: SessionStatus = SessionStatus.UPLOADED
    updated_at: str | None = None
    display_name: str | None = None
    rendered_file: StoredFile | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class InstructionSetLockRecord:
    session_id: str
    instruction_set_id: str
    instruction_set_content_hash: str
    snapshot_bytes: bytes
    created_at: str


@dataclass(frozen=True, slots=True)
class InstructionSetReferenceRecord:
    """Snapshot identity safe to expose without loading canonical bytes."""

    instruction_set_id: str
    instruction_set_content_hash: str
