"""Persistence-facing source records nested inside sessions."""

from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator

from app.files.records import StoredFile
from app.sources.formats import DocumentLayout, get_format_spec
from app.sources.kinds import SourceKind


def _require_source_format(
    file_format: str,
    *,
    kind: SourceKind,
    document_layout: DocumentLayout | None = None,
) -> None:
    try:
        spec = get_format_spec(file_format)
    except ValueError as exc:
        raise ValueError(f"unsupported {kind} source format") from exc
    if spec.kind != kind or spec.document_layout != document_layout:
        raise ValueError(f"format {file_format!r} is not valid for this {kind} source")


class SourceRecordBase(BaseModel):
    """Base persisted state for an immutable uploaded source file."""

    kind: SourceKind
    file: StoredFile

    model_config = {"extra": "forbid", "frozen": True}


class TextDocumentState(BaseModel):
    """Derived state for line-oriented text documents."""

    layout: Literal[DocumentLayout.TEXT] = DocumentLayout.TEXT
    line_count: int = Field(ge=0)
    character_count: int = Field(ge=0)

    model_config = {"extra": "forbid", "frozen": True}


class PdfDocumentState(BaseModel):
    """Derived state for fixed-layout PDF documents."""

    layout: Literal[DocumentLayout.FIXED] = DocumentLayout.FIXED
    page_count: int = Field(ge=1)

    model_config = {"extra": "forbid", "frozen": True}


class DocxDocumentState(BaseModel):
    """Derived state for DOCX Open XML processing and PDF preview."""

    layout: Literal[DocumentLayout.WORD_PROCESSING] = DocumentLayout.WORD_PROCESSING
    block_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    page_count: int = Field(ge=1)
    targetable_image_count: int = Field(default=0, ge=0)
    unsupported_image_count: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid", "frozen": True}


DocumentState: TypeAlias = Annotated[
    TextDocumentState | PdfDocumentState | DocxDocumentState,
    Field(discriminator="layout"),
]


class DocumentSourceRecord(SourceRecordBase):
    """Document source with format-specific derived state."""

    kind: Literal[SourceKind.DOCUMENT] = SourceKind.DOCUMENT
    state: DocumentState

    @model_validator(mode="after")
    def validate_format(self) -> DocumentSourceRecord:
        _require_source_format(
            self.file.format,
            kind=self.kind,
            document_layout=self.state.layout,
        )
        return self


class ImageSourceRecord(SourceRecordBase):
    """Raster image source."""

    kind: Literal[SourceKind.IMAGE] = SourceKind.IMAGE
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_format(self) -> ImageSourceRecord:
        _require_source_format(self.file.format, kind=self.kind)
        return self


class AudioSourceRecord(SourceRecordBase):
    """Audio or audio-bearing source."""

    kind: Literal[SourceKind.AUDIO] = SourceKind.AUDIO
    duration_seconds: float = Field(gt=0)
    sample_rate: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_format(self) -> AudioSourceRecord:
        _require_source_format(self.file.format, kind=self.kind)
        return self


SourceRecord: TypeAlias = DocumentSourceRecord | ImageSourceRecord | AudioSourceRecord
