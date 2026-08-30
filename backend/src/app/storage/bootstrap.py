"""Initialization of AIADR-managed SQLite state."""

from app.core.runtime import sensitive_debug_enabled
from app.storage import db, file_store, session_store
from app.storage.model_log_store import clear_sensitive_debug_fields


def initialize_storage() -> None:
    """Initialize new storage or validate existing storage without changing it."""
    if db.database_exists():
        db.validate_database()
        db.enable_wal()
    else:
        if file_store.managed_runtime_state_exists():
            raise RuntimeError(
                "The AIADR database is missing while managed session files exist. "
                "No managed files were modified. Back up or remove the configured "
                "data directory before starting fresh."
            )
        db.initialize_database()

    for session_id in session_store.list_pending_file_purges():
        file_store.purge_session_files(session_id)
        session_store.complete_file_purge(session_id)

    if not sensitive_debug_enabled():
        clear_sensitive_debug_fields()
