"""Create and resolve self-contained review export bundles."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from app.audit.event_log import list_events_through
from app.audit.events import AuditEvent, AuditEventType
from app.core.ids import new_export_id
from app.core.paths import exports_dir
from app.core.runtime import RuntimeMode, runtime_mode, sensitive_debug_enabled
from app.core.version import application_version, source_identity
from app.errors import ErrorCode, app_error
from app.files.descriptors import fingerprint_file
from app.files.hashing import sha256_file
from app.files.records import StoredFile
from app.instruction_sets import (
    InstructionSet,
    instruction_set_from_lock,
    require_session_instruction_set_lock,
)
from app.operations.export.audit_document import build_audit_document
from app.operations.export.signing import sign_manifest
from app.operations.output import OutputSnapshot, render_redacted_output
from app.sessions.records import InstructionSetLockRecord
from app.storage import (
    export_store,
    file_store,
    session_store,
)
from app.storage.transaction import transaction


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _bundle_filename() -> str:
    return "aiadr-export.zip"


def _validate_instruction_set(
    session_id: str,
) -> tuple[InstructionSetLockRecord, InstructionSet]:
    session_store.require_session(session_id)
    lock = require_session_instruction_set_lock(session_id)
    return lock, instruction_set_from_lock(lock)


def _write_bundle_contents(
    directory: Path,
    *,
    output: OutputSnapshot,
    lock: InstructionSetLockRecord,
    instruction_set: InstructionSet,
    export_id: str,
    bundle_filename: str,
) -> None:
    try:
        events = list_events_through(
            output.session_id,
            output.audit_boundary_hash,
        )
    except ValueError as exc:
        raise app_error(ErrorCode.INTERNAL_ERROR) from exc
    if (
        not events
        or events[-1]["event_type"] != AuditEventType.OUTPUT_RENDERED
        or events[-1]["event_hash"] != output.audit_boundary_hash
    ):
        raise app_error(ErrorCode.INTERNAL_ERROR)
    audit_boundary = events[-1]
    created_at = datetime.now(UTC).isoformat()
    _write_json(
        directory / "audit.json",
        build_audit_document(
            output=output,
            source_path=file_store.require_source_path(output.session_id, output.source.file),
            policy=instruction_set.policy,
            instruction_set_id=lock.instruction_set_id,
            instruction_set_content_hash=lock.instruction_set_content_hash,
            events=events,
            created_at=created_at,
        ),
    )
    if sensitive_debug_enabled():
        _write_json(
            directory / "model_run_log.json",
            {
                "contains_sensitive_debug_data": True,
                "runtime_mode": RuntimeMode.DEV,
                "logs": [log.model_dump(mode="json") for log in output.model_logs],
            },
        )
    (directory / "instruction_set_snapshot.json").write_bytes(lock.snapshot_bytes)
    shutil.copyfile(
        file_store.require_rendered_path(output.session_id, output.file),
        directory / output.file.filename,
    )

    file_entries = [
        {
            "filename": path.name,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(directory.iterdir())
        if path.is_file()
    ]
    source_identity_value = source_identity()
    manifest = sign_manifest(
        {
            "app": "AIADR",
            "application_version": application_version(),
            "source_revision": source_identity_value.revision,
            "source_modified": source_identity_value.modified,
            "export_schema_version": 1,
            "export_id": export_id,
            "session_id": output.session_id,
            "created_at": created_at,
            "runtime_mode": runtime_mode(),
            "contains_sensitive_debug_data": sensitive_debug_enabled(),
            "source_kind": output.source.kind,
            "source": fingerprint_file(output.source.file).model_dump(mode="json"),
            "rendered_file": {
                "file": output.file.filename,
                **fingerprint_file(output.file).model_dump(mode="json"),
            },
            "bundle": {"filename": bundle_filename},
            "audit_boundary": {
                "last_event_id": audit_boundary["event_id"],
                "last_event_hash": audit_boundary["event_hash"],
            },
            "instruction_set": {
                "id": lock.instruction_set_id,
                "content_hash": lock.instruction_set_content_hash,
            },
            "files": file_entries,
        }
    )
    _write_json(directory / "export_manifest.json", manifest)


def _build_zip(directory: Path, destination: Path) -> None:
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as bundle:
        for path in sorted(directory.iterdir()):
            if path.is_file():
                bundle.write(path, arcname=path.name)


async def create_export_bundle(session_id: str) -> StoredFile:
    """Render and persist one immutable export bundle."""
    lock, instruction_set = _validate_instruction_set(session_id)
    output = await render_redacted_output(session_id)
    export_id = new_export_id()
    bundle_filename = _bundle_filename()
    export_directory = exports_dir(output.session_id)
    temporary_zip = file_store.export_path(
        output.session_id,
        f".{export_id}.tmp",
    )
    temporary_zip.unlink(missing_ok=True)
    finalized: StoredFile | None = None

    try:
        with tempfile.TemporaryDirectory(
            prefix=f".{export_id}-",
            dir=export_directory,
        ) as working:
            working_directory = Path(working)
            _write_bundle_contents(
                working_directory,
                output=output,
                lock=lock,
                instruction_set=instruction_set,
                export_id=export_id,
                bundle_filename=bundle_filename,
            )
            _build_zip(working_directory, temporary_zip)

        finalized = file_store.finalize_export(
            output.session_id,
            temporary_zip,
            export_id=export_id,
            filename=bundle_filename,
        )
        with transaction() as tx:
            export_store.insert_with_connection(
                tx.connection,
                export_id=export_id,
                session_id=output.session_id,
                bundle=finalized,
            )
            tx.record(
                AuditEvent(
                    session_id=output.session_id,
                    event_type=AuditEventType.EXPORT_CREATED,
                    payload={
                        "export_id": export_id,
                        "source_kind": output.source.kind,
                        "rendered_file": fingerprint_file(output.file).model_dump(
                            mode="json"
                        ),
                        "bundle": fingerprint_file(finalized).model_dump(mode="json"),
                    },
                )
            )
    except BaseException:
        temporary_zip.unlink(missing_ok=True)
        if finalized is not None:
            file_store.export_path(
                output.session_id,
                finalized.stored_filename,
            ).unlink(missing_ok=True)
        raise
    return finalized


def get_latest_export_bundle(session_id: str) -> tuple[Path, str]:
    """Resolve the latest persisted export under the configured data root."""
    export = export_store.get_latest(session_id)
    return (
        file_store.require_export_path(session_id, export.stored_filename),
        export.filename,
    )
