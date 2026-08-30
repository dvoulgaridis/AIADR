"""Canonical metadata and validation for supported source file formats."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from app.errors import ErrorCode, app_error
from app.sources.kinds import SourceKind


class DocumentLayout(StrEnum):
    TEXT = "text"
    FIXED = "fixed"
    WORD_PROCESSING = "word_processing"


@dataclass(frozen=True, slots=True)
class SourceFormatSpec:
    """Immutable capabilities for one normalized source file format."""

    kind: SourceKind
    extensions: frozenset[str]
    accepted_mime_types: frozenset[str]
    canonical_mime_type: str
    document_layout: DocumentLayout | None = None


_SOURCE_FORMATS: Mapping[str, SourceFormatSpec] = MappingProxyType(
    {
        "aac": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".aac"}),
            accepted_mime_types=frozenset({"audio/aac"}),
            canonical_mime_type="audio/aac",
        ),
        "csv": SourceFormatSpec(
            kind=SourceKind.DOCUMENT,
            extensions=frozenset({".csv"}),
            accepted_mime_types=frozenset(
                {"application/csv", "application/vnd.ms-excel", "text/csv", "text/plain"}
            ),
            canonical_mime_type="application/csv",
            document_layout=DocumentLayout.TEXT,
        ),
        "docx": SourceFormatSpec(
            kind=SourceKind.DOCUMENT,
            extensions=frozenset({".docx"}),
            accepted_mime_types=frozenset(
                {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
            ),
            canonical_mime_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            document_layout=DocumentLayout.WORD_PROCESSING,
        ),
        "flac": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".flac"}),
            accepted_mime_types=frozenset({"audio/flac"}),
            canonical_mime_type="audio/flac",
        ),
        "jpeg": SourceFormatSpec(
            kind=SourceKind.IMAGE,
            extensions=frozenset({".jpeg", ".jpg"}),
            accepted_mime_types=frozenset({"image/jpeg"}),
            canonical_mime_type="image/jpeg",
        ),
        "m4a": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".m4a"}),
            accepted_mime_types=frozenset({"audio/mp4", "audio/x-m4a"}),
            canonical_mime_type="audio/mp4",
        ),
        "mp3": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".mp3"}),
            accepted_mime_types=frozenset({"audio/mpeg"}),
            canonical_mime_type="audio/mpeg",
        ),
        "mp4": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".mp4"}),
            accepted_mime_types=frozenset({"audio/mp4"}),
            canonical_mime_type="audio/mp4",
        ),
        "ogg": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".ogg"}),
            accepted_mime_types=frozenset({"application/ogg", "audio/ogg"}),
            canonical_mime_type="application/ogg",
        ),
        "opus": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".opus"}),
            accepted_mime_types=frozenset({"audio/ogg", "audio/opus"}),
            canonical_mime_type="audio/ogg",
        ),
        "pdf": SourceFormatSpec(
            kind=SourceKind.DOCUMENT,
            extensions=frozenset({".pdf"}),
            accepted_mime_types=frozenset({"application/pdf"}),
            canonical_mime_type="application/pdf",
            document_layout=DocumentLayout.FIXED,
        ),
        "png": SourceFormatSpec(
            kind=SourceKind.IMAGE,
            extensions=frozenset({".png"}),
            accepted_mime_types=frozenset({"image/png"}),
            canonical_mime_type="image/png",
        ),
        "txt": SourceFormatSpec(
            kind=SourceKind.DOCUMENT,
            extensions=frozenset({".txt"}),
            accepted_mime_types=frozenset({"text/plain"}),
            canonical_mime_type="text/plain",
            document_layout=DocumentLayout.TEXT,
        ),
        "wav": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".wav"}),
            accepted_mime_types=frozenset({"audio/wav", "audio/x-wav"}),
            canonical_mime_type="audio/wav",
        ),
        "webm": SourceFormatSpec(
            kind=SourceKind.AUDIO,
            extensions=frozenset({".webm"}),
            accepted_mime_types=frozenset({"audio/webm"}),
            canonical_mime_type="audio/webm",
        ),
        "webp": SourceFormatSpec(
            kind=SourceKind.IMAGE,
            extensions=frozenset({".webp"}),
            accepted_mime_types=frozenset({"image/webp"}),
            canonical_mime_type="image/webp",
        ),
    }
)

_FORMAT_BY_EXTENSION: Mapping[str, str] = MappingProxyType(
    {
        extension: file_format
        for file_format, spec in _SOURCE_FORMATS.items()
        for extension in spec.extensions
    }
)


def get_format_spec(file_format: str) -> SourceFormatSpec:
    """Return the specification for one canonical source format."""
    try:
        return _SOURCE_FORMATS[file_format]
    except KeyError as exc:
        raise ValueError(f"Unsupported or noncanonical source format: {file_format}") from exc


def resolve_upload_format(filename: str, mime_type: str) -> str:
    """Validate upload metadata and return its normalized exact format."""
    suffix = Path(filename).suffix.lower()
    file_format = _FORMAT_BY_EXTENSION.get(suffix)
    if file_format is not None:
        spec = _SOURCE_FORMATS[file_format]
        if mime_type in spec.accepted_mime_types:
            return file_format
    raise app_error(
        ErrorCode.UNSUPPORTED_UPLOAD_TYPE,
        details={
            "filename": Path(filename).name.strip() or "upload",
            "mime_type": mime_type or "unknown",
        },
    )


def kind_for_format(file_format: str) -> SourceKind:
    """Return the source kind for one supported exact file format."""
    return get_format_spec(file_format).kind


def canonical_mime_type(file_format: str) -> str:
    """Return the canonical persisted MIME type for a supported format."""
    return get_format_spec(file_format).canonical_mime_type


def validate_kind_format(kind: str, file_format: str) -> SourceKind:
    """Validate one persisted source-kind and file-format combination."""
    try:
        persisted_kind = SourceKind(kind)
        expected = kind_for_format(file_format)
    except ValueError as exc:
        raise app_error(
            ErrorCode.SOURCE_INTEGRITY_ERROR,
            details={"kind": kind, "format": file_format},
        ) from exc
    if persisted_kind is not expected:
        raise app_error(
            ErrorCode.SOURCE_INTEGRITY_ERROR,
            details={
                "kind": kind,
                "format": file_format,
                "expected_kind": expected,
            },
        )
    return expected
