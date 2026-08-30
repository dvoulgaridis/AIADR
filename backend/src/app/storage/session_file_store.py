"""SQLite persistence for uploaded and rendered session files."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, assert_never

from pydantic import ValidationError

from app.errors import ErrorCode, app_error
from app.files.records import StoredFile
from app.sources.formats import DocumentLayout, get_format_spec, validate_kind_format
from app.sources.kinds import SourceKind
from app.sources.records import (
    AudioSourceRecord,
    DocumentSourceRecord,
    DocxDocumentState,
    ImageSourceRecord,
    PdfDocumentState,
    SourceRecord,
    TextDocumentState,
)


def _file_from_row(row: Any) -> StoredFile:
    try:
        return StoredFile(
            filename=row["filename"],
            stored_filename=row["stored_filename"],
            format=row["format"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            sha256=row["sha256"],
        )
    except ValidationError as exc:
        raise app_error(
            ErrorCode.SOURCE_INTEGRITY_ERROR,
            details={"kind": str(row["kind"]), "format": str(row["format"])},
        ) from exc


def _source_from_row(row: Any) -> SourceRecord:
    file = _file_from_row(row)
    kind = validate_kind_format(str(row["kind"]), file.format)
    spec = get_format_spec(file.format)
    if spec.document_layout is DocumentLayout.TEXT:
        return DocumentSourceRecord(
            file=file,
            state=TextDocumentState(
                line_count=row["line_count"],
                character_count=row["character_count"],
            ),
        )
    if spec.document_layout is DocumentLayout.FIXED:
        return DocumentSourceRecord(
            file=file,
            state=PdfDocumentState(
                page_count=row["page_count"],
            ),
        )
    if spec.document_layout is DocumentLayout.WORD_PROCESSING:
        return DocumentSourceRecord(
            file=file,
            state=DocxDocumentState(
                block_count=row["block_count"],
                character_count=row["character_count"],
                page_count=row["page_count"],
                targetable_image_count=row["targetable_image_count"],
                unsupported_image_count=row["unsupported_image_count"],
            ),
        )
    if kind is SourceKind.IMAGE:
        return ImageSourceRecord(file=file, width=row["width"], height=row["height"])
    if kind is SourceKind.AUDIO:
        return AudioSourceRecord(
            file=file,
            duration_seconds=row["duration_seconds"],
            sample_rate=row["sample_rate"],
        )
    raise ValueError(f"Unsupported persisted source: kind={kind}, format={file.format}")


def _rendered_file_from_row(row: Any, source_kind: SourceKind) -> StoredFile:
    file = _file_from_row(row)
    kind = validate_kind_format(str(row["kind"]), file.format)
    if kind != source_kind:
        raise app_error(
            ErrorCode.SOURCE_INTEGRITY_ERROR,
            details={
                "kind": kind,
                "format": file.format,
                "source_kind": source_kind,
            },
        )
    return file


@dataclass(frozen=True, slots=True)
class _SourceMeasurements:
    """Nullable columns derived from one concrete source record."""

    line_count: int | None = None
    character_count: int | None = None
    page_count: int | None = None
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    sample_rate: int | None = None
    block_count: int | None = None
    targetable_image_count: int | None = None
    unsupported_image_count: int | None = None


def _measurements(source: SourceRecord) -> _SourceMeasurements:
    if isinstance(source, DocumentSourceRecord):
        match source.state:
            case TextDocumentState() as state:
                return _SourceMeasurements(
                    line_count=state.line_count,
                    character_count=state.character_count,
                )
            case PdfDocumentState() as state:
                return _SourceMeasurements(page_count=state.page_count)
            case DocxDocumentState() as state:
                return _SourceMeasurements(
                    character_count=state.character_count,
                    page_count=state.page_count,
                    block_count=state.block_count,
                    targetable_image_count=state.targetable_image_count,
                    unsupported_image_count=state.unsupported_image_count,
                )
            case unexpected_state:
                assert_never(unexpected_state)
    if isinstance(source, ImageSourceRecord):
        return _SourceMeasurements(width=source.width, height=source.height)
    if isinstance(source, AudioSourceRecord):
        return _SourceMeasurements(
            duration_seconds=source.duration_seconds,
            sample_rate=source.sample_rate,
        )
    assert_never(source)


def put_source_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    source: SourceRecord,
) -> None:
    """Insert the immutable source relation using the caller's transaction."""
    file = source.file
    measurements = _measurements(source)
    validate_kind_format(source.kind, file.format)
    connection.execute(
        """
        INSERT INTO session_files (
            session_id, role, kind, format, filename, stored_filename,
            mime_type, size_bytes, sha256, line_count, character_count,
            page_count, width, height,
            duration_seconds, sample_rate, block_count,
            targetable_image_count, unsupported_image_count
        ) VALUES (?, 'source', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            source.kind,
            file.format,
            file.filename,
            file.stored_filename,
            file.mime_type,
            file.size_bytes,
            file.sha256,
            measurements.line_count,
            measurements.character_count,
            measurements.page_count,
            measurements.width,
            measurements.height,
            measurements.duration_seconds,
            measurements.sample_rate,
            measurements.block_count,
            measurements.targetable_image_count,
            measurements.unsupported_image_count,
        ),
    )


def replace_source_metadata_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    source: SourceRecord,
) -> SourceRecord:
    """Replace derived source measurements while preserving file identity."""
    current = require_source_with_connection(connection, session_id)
    if type(current) is not type(source) or current.file != source.file:
        raise ValueError("source file identity and concrete source type are immutable")
    measurements = _measurements(source)
    connection.execute(
        """
        UPDATE session_files SET
            line_count = ?,
            character_count = ?,
            page_count = ?,
            width = ?,
            height = ?,
            duration_seconds = ?,
            sample_rate = ?,
            block_count = ?,
            targetable_image_count = ?,
            unsupported_image_count = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE session_id = ? AND role = 'source'
        """,
        (
            measurements.line_count,
            measurements.character_count,
            measurements.page_count,
            measurements.width,
            measurements.height,
            measurements.duration_seconds,
            measurements.sample_rate,
            measurements.block_count,
            measurements.targetable_image_count,
            measurements.unsupported_image_count,
            session_id,
        ),
    )
    return require_source_with_connection(connection, session_id)


def set_rendered_file_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    source: SourceRecord,
    file: StoredFile,
) -> None:
    """Replace the current rendered relation using source-controlled kind."""
    validate_kind_format(source.kind, file.format)
    connection.execute(
        """
        INSERT INTO session_files (
            session_id, role, kind, format, filename, stored_filename,
            mime_type, size_bytes, sha256
        ) VALUES (?, 'rendered', ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, role) DO UPDATE SET
            kind = excluded.kind,
            format = excluded.format,
            filename = excluded.filename,
            stored_filename = excluded.stored_filename,
            mime_type = excluded.mime_type,
            size_bytes = excluded.size_bytes,
            sha256 = excluded.sha256,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            session_id,
            source.kind,
            file.format,
            file.filename,
            file.stored_filename,
            file.mime_type,
            file.size_bytes,
            file.sha256,
        ),
    )


def require_source_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
) -> SourceRecord:
    row = connection.execute(
        "SELECT * FROM session_files WHERE session_id = ? AND role = 'source'",
        (session_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Session {session_id} has no source relation")
    return _source_from_row(row)


def get_rendered_file_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
) -> StoredFile | None:
    source = require_source_with_connection(connection, session_id)
    row = connection.execute(
        "SELECT * FROM session_files WHERE session_id = ? AND role = 'rendered'",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return _rendered_file_from_row(row, source.kind)


def get_relations_with_connection(
    connection: sqlite3.Connection,
    session_ids: Sequence[str],
) -> dict[str, tuple[SourceRecord, StoredFile | None]]:
    """Load source/rendered relations for multiple sessions in one query."""
    if not session_ids:
        return {}
    placeholders = ", ".join("?" for _ in session_ids)
    rows = connection.execute(
        f"""
        SELECT * FROM session_files
        WHERE session_id IN ({placeholders})
        ORDER BY session_id, role
        """,
        tuple(session_ids),
    ).fetchall()
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        grouped.setdefault(row["session_id"], {})[row["role"]] = row

    relations: dict[str, tuple[SourceRecord, StoredFile | None]] = {}
    for session_id in session_ids:
        source_row = grouped.get(session_id, {}).get("source")
        if source_row is None:
            raise ValueError(f"Session {session_id} has no source relation")
        source = _source_from_row(source_row)
        rendered_row = grouped[session_id].get("rendered")
        relations[session_id] = (
            source,
            (
                _rendered_file_from_row(rendered_row, source.kind)
                if rendered_row is not None
                else None
            ),
        )
    return relations
