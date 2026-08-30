"""Create review sessions from caller-owned upload streams."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from app.audit.events import ActorType, AuditEvent, AuditEventType
from app.core.ids import new_session_id
from app.files.descriptors import fingerprint_file
from app.files.records import StoredFile
from app.operations.docx import inspect_source
from app.preprocessing.image import inspect_image
from app.preprocessing.pdf import inspect_pdf
from app.sessions.records import SessionRecord
from app.sources.audio import inspect_audio
from app.sources.docx_images import DocxImageOccurrence
from app.sources.docx_text import DocxTextBlock
from app.sources.formats import DocumentLayout, get_format_spec
from app.sources.kinds import SourceKind
from app.sources.pdf_text import PdfTextLine
from app.sources.records import (
    AudioSourceRecord,
    DocumentSourceRecord,
    DocxDocumentState,
    ImageSourceRecord,
    PdfDocumentState,
    SourceRecord,
    TextDocumentState,
)
from app.storage import session_store, source_store
from app.storage.file_store import (
    purge_session_files,
    require_source_path,
    save_upload,
)
from app.storage.transaction import transaction


def _inspect_text(path: Path) -> tuple[int, int]:
    line_count = 0
    character_count = 0
    with path.open("r", encoding="utf-8", errors="replace", newline="") as source:
        for line in source:
            line_count += 1
            character_count += len(line)
    return line_count, character_count


def _build_source(session_id: str, file: StoredFile) -> SourceRecord:
    path = require_source_path(session_id, file)
    spec = get_format_spec(file.format)
    match spec.kind, spec.document_layout:
        case SourceKind.DOCUMENT, DocumentLayout.TEXT:
            line_count, character_count = _inspect_text(path)
            return DocumentSourceRecord(
                file=file,
                state=TextDocumentState(
                    line_count=line_count,
                    character_count=character_count,
                ),
            )
        case SourceKind.DOCUMENT, DocumentLayout.FIXED:
            pdf = inspect_pdf(path)
            return DocumentSourceRecord(
                file=file,
                state=PdfDocumentState(page_count=pdf.page_count),
            )
        case SourceKind.IMAGE, None:
            width, height = inspect_image(path)
            return ImageSourceRecord(file=file, width=width, height=height)
        case SourceKind.AUDIO, None:
            audio = inspect_audio(path)
            return AudioSourceRecord(
                file=file,
                duration_seconds=audio.duration_seconds,
                sample_rate=audio.sample_rate,
            )
        case _:
            raise ValueError(
                f"Unsupported source format configuration: {file.format}",
            )


async def create_session_from_upload(
    *,
    stream: BinaryIO,
    filename: str,
    mime_type: str,
) -> SessionRecord:
    """Validate, inspect, and atomically publish one uploaded source."""
    session_id = new_session_id()
    file = await asyncio.to_thread(
        save_upload,
        session_id,
        stream,
        filename=filename,
        mime_type=mime_type,
    )
    try:
        source: SourceRecord
        blocks: tuple[DocxTextBlock, ...] = ()
        image_occurrences: tuple[DocxImageOccurrence, ...] = ()
        document_lines: tuple[PdfTextLine, ...] = ()
        if get_format_spec(file.format).document_layout is DocumentLayout.WORD_PROCESSING:
            inspection = await inspect_source(session_id, file)
            source = inspection.source
            blocks = inspection.text_blocks
            document_lines = inspection.preview_lines
            image_occurrences = inspection.image_occurrences
        else:
            source = await asyncio.to_thread(_build_source, session_id, file)
        timestamp = datetime.now(UTC).isoformat()
        session = SessionRecord(
            session_id=session_id,
            source=source,
            created_at=timestamp,
            updated_at=timestamp,
            display_name=session_store.display_name_for_filename(file.filename),
        )
        fingerprint = fingerprint_file(file).model_dump(mode="json")
        with transaction() as tx:
            session_store.put_session_with_connection(tx.connection, session)
            if isinstance(source, DocumentSourceRecord) and isinstance(
                source.state, DocxDocumentState
            ):
                source_store.replace_docx_blocks_with_connection(
                    tx.connection,
                    session_id,
                    blocks,
                )
                source_store.replace_pdf_lines_with_connection(
                    tx.connection,
                    session_id,
                    document_lines,
                )
                source_store.replace_docx_image_occurrences_with_connection(
                    tx.connection,
                    session_id,
                    image_occurrences,
                )
            tx.record(
                AuditEvent(
                    session_id=session_id,
                    event_type=AuditEventType.SESSION_CREATED,
                    payload={
                        "source_kind": source.kind,
                        "file": fingerprint,
                    },
                )
            )
            tx.record(
                AuditEvent(
                    session_id=session_id,
                    event_type=AuditEventType.FILE_UPLOADED,
                    payload={"source_kind": source.kind, "file": fingerprint},
                    actor_id="Reviewer-001",
                    actor_type=ActorType.REVIEWER,
                )
            )
        return session
    except BaseException:
        purge_session_files(session_id)
        raise
