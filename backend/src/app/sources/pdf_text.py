"""Stable PDF text-line records and normalization."""

from __future__ import annotations

import re

from pydantic import BaseModel


class PdfTextLine(BaseModel):
    """A deterministic text line extracted from one PDF page."""

    line_id: str
    page: int
    text: str


def pdf_line_id(index: int) -> str:
    """Return the stable page-local ID for a zero-based line index."""
    return f"l{index + 1:04d}"


def normalize_pdf_line_text(value: str) -> str:
    """Normalize one extracted line for stable exact-text matching."""
    return re.sub(r"\s+", " ", value).strip()
