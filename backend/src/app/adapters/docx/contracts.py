"""Private contracts for the stateless DOCX processor."""

from __future__ import annotations

from enum import StrEnum

from app.domain.finding import DocxTextLocator
from app.sources.docx_text import DocxStoryKind, DocxTextBlock
from pydantic import BaseModel, Field, model_validator


class DocxProcessorOperation(StrEnum):
    HANDSHAKE = "handshake"
    INSPECT = "inspect"
    RENDER = "render"


class DocxProcessorErrorCode(StrEnum):
    PROTOCOL_ERROR = "protocol_error"
    PROCESSOR_FAILURE = "processor_failure"
    INVALID_DOCX = "invalid_docx"
    INVALID_TARGET = "invalid_target"
    OVERLAPPING_TARGETS = "overlapping_targets"
    INVALID_EFFECT = "invalid_effect"
    INVALID_REPLACEMENT = "invalid_replacement"
    UNSAFE_PATH = "unsafe_path"
    SOURCE_HASH_MISMATCH = "source_hash_mismatch"
    UNSUPPORTED_DOCX_FEATURE = "unsupported_docx_feature"


class ProcessorError(BaseModel):
    code: DocxProcessorErrorCode
    message: str
    feature: str | None = None

    model_config = {"extra": "forbid", "frozen": True}


class ProcessorResponse(BaseModel):
    request_id: str
    ok: bool
    payload: dict[str, object] | None
    error: ProcessorError | None
    working_set_bytes: int = Field(ge=0)

    model_config = {"extra": "forbid", "frozen": True}


class HandshakeResult(BaseModel):
    openxml_sdk_version: str
    operations: tuple[DocxProcessorOperation, ...]

    model_config = {"extra": "forbid", "frozen": True}


class SanitationSummary(BaseModel):
    comments_removed: int = Field(ge=0)
    properties_removed: int = Field(ge=0)

    model_config = {"extra": "forbid", "frozen": True}


class ProcessorImageOccurrence(BaseModel):
    """Processor-private structural picture evidence awaiting bitmap normalization."""

    id: str = Field(pattern=r"^pic_[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)
    story_kind: DocxStoryKind
    part_uri: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    source_asset: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]+$")
    crop_left: int = Field(ge=0, le=100000)
    crop_top: int = Field(ge=0, le=100000)
    crop_right: int = Field(ge=0, le=100000)
    crop_bottom: int = Field(ge=0, le=100000)
    flip_horizontal: bool
    flip_vertical: bool
    targetable: bool
    unsupported_reason: str | None = None

    @model_validator(mode="after")
    def validate_targetability(self) -> ProcessorImageOccurrence:
        if self.targetable != (self.source_asset is not None and self.unsupported_reason is None):
            raise ValueError("processor picture targetability is inconsistent")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class DocxInspectResult(BaseModel):
    character_count: int = Field(ge=0)
    blocks: tuple[DocxTextBlock, ...]
    image_occurrences: tuple[ProcessorImageOccurrence, ...]
    document_sha256: str
    sanitation: SanitationSummary

    @model_validator(mode="after")
    def validate_inspection(self) -> DocxInspectResult:
        if tuple(block.ordinal for block in self.blocks) != tuple(range(len(self.blocks))):
            raise ValueError("DOCX blocks must have contiguous ordinals")
        if len({block.block_id for block in self.blocks}) != len(self.blocks):
            raise ValueError("DOCX block IDs must be unique")
        if self.character_count != sum(len(block.text) for block in self.blocks):
            raise ValueError("DOCX character count must match canonical blocks")
        if tuple(item.ordinal for item in self.image_occurrences) != tuple(
            range(len(self.image_occurrences))
        ):
            raise ValueError("DOCX picture occurrences must have contiguous ordinals")
        if len({item.id for item in self.image_occurrences}) != len(self.image_occurrences):
            raise ValueError("DOCX picture occurrence IDs must be unique")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class DocxRenderLayer(BaseModel):
    layer_id: str
    target: DocxTextLocator
    replacement_text: str

    model_config = {"extra": "forbid", "frozen": True}


class DocxImageReplacement(BaseModel):
    occurrence_id: str = Field(pattern=r"^pic_[0-9a-f]{64}$")
    replacement_path: str = Field(min_length=1)
    replacement_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = {"extra": "forbid", "frozen": True}


class DocxRenderResult(BaseModel):
    document_sha256: str
    sanitation: SanitationSummary

    model_config = {"extra": "forbid", "frozen": True}
