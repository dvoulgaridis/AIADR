"""Projection from internal session records to generated API contracts."""

from __future__ import annotations

from datetime import datetime

from app.api import contracts as api_contracts
from app.files.descriptors import describe_file
from app.sessions.records import InstructionSetReferenceRecord, SessionRecord
from app.sources.records import (
    AudioSourceRecord,
    DocumentSourceRecord,
    ImageSourceRecord,
)


def to_api_source(record: SessionRecord) -> api_contracts.Source:
    """Build the source variant appropriate for an internal session record."""
    source = record.source
    file = api_contracts.FileDescriptor.model_validate(
        describe_file(source.file).model_dump(mode="json")
    )
    value: api_contracts.DocumentSource | api_contracts.ImageSource | api_contracts.AudioSource
    if isinstance(source, DocumentSourceRecord):
        value = api_contracts.DocumentSource.model_validate(
            {
                "kind": source.kind,
                "file": file,
                "state": source.state.model_dump(mode="json"),
            }
        )
    elif isinstance(source, ImageSourceRecord):
        value = api_contracts.ImageSource(
            kind="image",
            file=file,
            width=source.width,
            height=source.height,
        )
    elif isinstance(source, AudioSourceRecord):
        value = api_contracts.AudioSource(
            kind="audio",
            file=file,
            duration_seconds=source.duration_seconds,
            sample_rate=source.sample_rate,
        )
    else:
        raise TypeError(f"Unsupported source record: {type(source).__name__}")
    return api_contracts.Source(root=value)


def public_error_for(error_message: str | None) -> str | None:
    """Return a safe summary without exposing provider data or local paths."""
    if error_message is None:
        return None
    return "The operation failed. Review the session logs for details."


def to_api_session(
    record: SessionRecord,
    *,
    analysis_active: bool,
    instruction_set: InstructionSetReferenceRecord | None,
) -> api_contracts.Session:
    """Project an internal record into the public session resource."""
    return api_contracts.Session(
        session_id=record.session_id,
        source=to_api_source(record),
        status=api_contracts.SessionStatus(record.status),
        analysis_active=analysis_active,
        instruction_set=(
            api_contracts.InstructionSetReference(
                id=instruction_set.instruction_set_id,
                content_hash=instruction_set.instruction_set_content_hash,
            )
            if instruction_set is not None
            else None
        ),
        display_name=record.display_name,
        created_at=datetime.fromisoformat(record.created_at),
        updated_at=datetime.fromisoformat(record.updated_at) if record.updated_at else None,
        rendered_file=(
            api_contracts.FileDescriptor.model_validate(
                describe_file(record.rendered_file).model_dump(mode="json"),
            )
            if record.rendered_file is not None
            else None
        ),
        public_error=public_error_for(record.error_message),
    )
