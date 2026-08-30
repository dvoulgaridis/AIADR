"""Immutable identity for files managed by AIADR."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class StoredFile(BaseModel):
    """Complete persisted identity of finalized file bytes."""

    filename: str = Field(min_length=1)
    stored_filename: str = Field(min_length=1)
    format: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str

    @field_validator("filename", "stored_filename")
    @classmethod
    def require_filename_only(cls, value: str) -> str:
        if Path(value).name != value:
            raise ValueError("file names must not contain path components")
        return value

    @field_validator("format")
    @classmethod
    def require_canonical_format(cls, value: str) -> str:
        if not value or value != value.strip().lower() or value.startswith("."):
            raise ValueError("file format must use its canonical internal spelling")
        return value

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ValueError("sha256 must be a lowercase SHA-256 digest")
        return normalized

    model_config = {"extra": "forbid", "frozen": True}
