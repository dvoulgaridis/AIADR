"""Durable evidence for raster pictures embedded in DOCX sources."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.domain.finding import TargetRegion
from app.sources.docx_text import DocxStoryKind


class DocxImageOccurrence(BaseModel):
    """One placed picture and its normalized visible analysis asset."""

    occurrence_id: str = Field(pattern=r"^pic_[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)
    story_kind: DocxStoryKind
    part_uri: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    asset_filename: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._-]+$")
    normalized_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    targetable: bool
    unsupported_reason: str | None = None

    @model_validator(mode="after")
    def validate_targetability(self) -> DocxImageOccurrence:
        evidence = (
            self.asset_filename,
            self.normalized_sha256,
            self.width_px,
            self.height_px,
        )
        if self.targetable:
            if any(value is None for value in evidence) or self.unsupported_reason is not None:
                raise ValueError("targetable DOCX pictures require complete normalized evidence")
        elif self.unsupported_reason is None:
            raise ValueError("unsupported DOCX pictures require a reason")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class DocxPicturePlacement(BaseModel):
    """Renderer-derived page placement for one durable DOCX picture occurrence."""

    occurrence_id: str = Field(pattern=r"^pic_[0-9a-f]{64}$")
    page: int = Field(ge=1)
    region: TargetRegion

    model_config = {"extra": "forbid", "frozen": True}
