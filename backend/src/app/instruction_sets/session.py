"""Restore the immutable instruction set bound to a review session."""

from __future__ import annotations

from app.errors import ErrorCode, app_error
from app.instruction_sets.instruction_set import InstructionSet, instruction_set_from_snapshot
from app.sessions.records import InstructionSetLockRecord
from app.storage import session_store


def require_session_instruction_set_lock(session_id: str) -> InstructionSetLockRecord:
    """Return the persisted instruction-set binding owned by a session."""
    lock = session_store.get_instruction_set_lock(session_id)
    if lock is None:
        raise app_error(
            ErrorCode.INSTRUCTION_SET_NOT_LOCKED,
            details={"session_id": session_id},
        )
    return lock


def instruction_set_from_lock(lock: InstructionSetLockRecord) -> InstructionSet:
    """Verify and restore an instruction set from its persisted binding."""
    try:
        return instruction_set_from_snapshot(
            lock.snapshot_bytes,
            expected_id=lock.instruction_set_id,
            expected_hash=lock.instruction_set_content_hash,
        )
    except ValueError as exc:
        raise app_error(
            ErrorCode.INSTRUCTION_SET_INTEGRITY_ERROR,
            details={"session_id": lock.session_id},
        ) from exc


def require_session_instruction_set(session_id: str) -> InstructionSet:
    """Return and verify the canonical snapshot owned by a session."""
    return instruction_set_from_lock(require_session_instruction_set_lock(session_id))
