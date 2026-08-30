"""Inspect PDFs and render page images for visual analysis."""

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from app.errors import ErrorCode, app_error
from app.preprocessing.image import write_analysis_jpeg
from app.sources.pdf_text import PdfTextLine, normalize_pdf_line_text, pdf_line_id

PDF_ANALYSIS_DPI = 150


def _require_page_count(page_count: int) -> int:
    if page_count < 1:
        raise app_error(
            ErrorCode.REQUEST_VALIDATION_FAILED,
            message="The PDF contains no pages.",
        )
    return page_count


@dataclass(frozen=True, slots=True)
class PdfInfo:
    """Intrinsic metadata inspected from a PDF source."""

    page_count: int


@dataclass(frozen=True, slots=True)
class PdfPageInput:
    """One rendered page image and its stable source page number."""

    page: int
    page_count: int
    image_path: Path
    mime_type: str


@dataclass(frozen=True, slots=True)
class PdfTextIndex:
    """Page count and deterministic text lines extracted from one PDF."""

    page_count: int
    lines: tuple[PdfTextLine, ...]


def inspect_pdf(file_path: Path) -> PdfInfo:
    """Read PDF metadata without rendering pages."""
    pdf = pdfium.PdfDocument(str(file_path))
    try:
        return PdfInfo(page_count=_require_page_count(len(pdf)))
    finally:
        pdf.close()


def _extract_pdf_text_lines(
    page_source: object,
    page_number: int,
) -> tuple[PdfTextLine, ...]:
    """Extract deterministic lines while the PDFium page is open."""
    text_page = page_source.get_textpage()  # type: ignore[attr-defined]
    try:
        text = text_page.get_text_range()
    finally:
        text_page.close()
    lines = [
        normalized for line in text.splitlines() if (normalized := normalize_pdf_line_text(line))
    ]
    return tuple(
        PdfTextLine(line_id=pdf_line_id(index), page=page_number, text=line)
        for index, line in enumerate(lines)
    )


def extract_pdf_text_index(source_path: Path) -> PdfTextIndex:
    """Extract page-aware text without rendering inference images."""
    pdf = pdfium.PdfDocument(str(source_path))
    try:
        page_count = _require_page_count(len(pdf))
        lines: list[PdfTextLine] = []
        for page_index in range(page_count):
            page = pdf[page_index]
            try:
                lines.extend(_extract_pdf_text_lines(page, page_index + 1))
            finally:
                page.close()
        return PdfTextIndex(page_count=page_count, lines=tuple(lines))
    finally:
        pdf.close()


def build_pdf_page_inputs(
    source_path: Path,
    workspace: Path,
) -> tuple[PdfPageInput, ...]:
    """Render every page and close all PDF resources before returning."""
    pdf = pdfium.PdfDocument(str(source_path))
    try:
        page_count = _require_page_count(len(pdf))
        workspace.mkdir(parents=True, exist_ok=True)
        inputs: list[PdfPageInput] = []
        for page_index in range(page_count):
            page_number = page_index + 1
            pdf_page = pdf[page_index]
            try:
                bitmap = pdf_page.render(scale=PDF_ANALYSIS_DPI / 72)
                try:
                    image = bitmap.to_pil()
                finally:
                    bitmap.close()
                try:
                    image_path = workspace / f"page-{page_number}.jpg"
                    write_analysis_jpeg(image, image_path)
                finally:
                    image.close()
                inputs.append(
                    PdfPageInput(
                        page=page_number,
                        page_count=page_count,
                        image_path=image_path,
                        mime_type="image/jpeg",
                    )
                )
            finally:
                pdf_page.close()
        return tuple(inputs)
    finally:
        pdf.close()
