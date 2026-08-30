"""Canonical text evidence extracted from supported DOCX packages."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DocxStoryKind(StrEnum):
    BODY = "body"
    HEADER = "header"
    FOOTER = "footer"
    FOOTNOTE = "footnote"
    ENDNOTE = "endnote"


class DocxTextBlock(BaseModel):
    """One stable block in the canonical DOCX text projection."""

    block_id: str = Field(pattern=r"^b_[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)
    story_kind: DocxStoryKind
    part_uri: str = Field(min_length=1)
    structural_path: str = Field(min_length=1)
    text: str

    model_config = {"extra": "forbid", "frozen": True}
