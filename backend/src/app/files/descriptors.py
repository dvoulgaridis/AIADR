"""Portable file projections for API, audit, and export boundaries."""

from pydantic import BaseModel, Field

from app.files.records import StoredFile


class FileDescriptor(BaseModel):
    """User-facing identity of finalized bytes without an internal storage name."""

    format: str
    filename: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = {"extra": "forbid", "frozen": True}


class FileFingerprint(BaseModel):
    """Filename-free file metadata for audit and export evidence."""

    format: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = {"extra": "forbid", "frozen": True}


def describe_file(file: StoredFile) -> FileDescriptor:
    """Project stored identity into its safe portable representation."""
    return FileDescriptor(
        format=file.format,
        filename=file.filename,
        mime_type=file.mime_type,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
    )


def fingerprint_file(file: StoredFile) -> FileFingerprint:
    """Project stored bytes without exposing either file name."""
    return FileFingerprint(
        format=file.format,
        mime_type=file.mime_type,
        size_bytes=file.size_bytes,
        sha256=file.sha256,
    )
