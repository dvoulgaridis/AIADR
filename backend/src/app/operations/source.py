"""Application workflows for source delivery and browser previews."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.domain.finding import DocxTextLocator, FileImageSurface
from app.errors import ErrorCode, app_error
from app.operations.docx import get_picture_placements, get_preview_path
from app.redaction.audio_renderer import render_redacted_audio
from app.redaction.image_renderer import image_layers_for_surface, render_redacted_image
from app.sources.docx_images import DocxPicturePlacement
from app.sources.docx_targets import resolve_pdf_selection
from app.sources.pdf_text import PdfTextLine
from app.sources.records import (
    AudioSourceRecord,
    DocumentSourceRecord,
    DocxDocumentState,
    ImageSourceRecord,
    PdfDocumentState,
)
from app.storage import review_store, session_store, source_store
from app.storage.file_store import output_path, require_source_path


@dataclass(frozen=True, slots=True)
class FileArtifact:
    """A file prepared for delivery by the HTTP boundary."""

    path: Path
    mime_type: str | None
    filename: str | None = None
    delete_after_send: bool = False


def _temporary_preview_path(session_id: str, *, prefix: str, suffix: str) -> Path:
    preview_directory = output_path(session_id, f"{prefix}{suffix}").parent
    with tempfile.NamedTemporaryFile(
        prefix=prefix,
        suffix=suffix,
        dir=preview_directory,
        delete=False,
    ) as temporary_file:
        return Path(temporary_file.name)


def get_uploaded_source(session_id: str) -> FileArtifact:
    """Resolve the immutable uploaded source."""
    session = session_store.require_session(session_id)
    return FileArtifact(
        path=require_source_path(session_id, session.source.file),
        mime_type=session.source.file.mime_type,
        filename=session.source.file.filename,
    )


async def get_source_preview(session_id: str) -> FileArtifact:
    """Return the browser-facing preview for one source."""
    session = session_store.require_session(session_id)
    source = session.source
    source_path = require_source_path(session_id, source.file)

    if isinstance(source, DocumentSourceRecord) and isinstance(
        source.state,
        DocxDocumentState,
    ):
        preview = await get_preview_path(
            session_id,
            source,
            review_store.get_layers(session_id, []),
        )
        return FileArtifact(path=preview, mime_type="application/pdf")

    if isinstance(source, AudioSourceRecord):
        audio_preview = _temporary_preview_path(
            session_id,
            prefix="audio-preview-",
            suffix=".wav",
        )
        try:
            await asyncio.to_thread(
                render_redacted_audio,
                source_path,
                review_store.get_layers(session_id, []),
                audio_preview,
            )
        except BaseException:
            audio_preview.unlink(missing_ok=True)
            raise
        return FileArtifact(
            path=audio_preview,
            mime_type="audio/wav",
            delete_after_send=True,
        )

    if isinstance(source, ImageSourceRecord):
        image_layers = image_layers_for_surface(
            review_store.get_layers(session_id, []),
            FileImageSurface(),
        )
        if not image_layers:
            return FileArtifact(path=source_path, mime_type=source.file.mime_type)

        image_preview = _temporary_preview_path(
            session_id,
            prefix="image-preview-",
            suffix=".png",
        )
        try:
            await asyncio.to_thread(
                render_redacted_image,
                source_path,
                image_layers,
                image_preview,
            )
        except BaseException:
            image_preview.unlink(missing_ok=True)
            raise
        return FileArtifact(
            path=image_preview,
            mime_type="image/png",
            delete_after_send=True,
        )

    if isinstance(source, DocumentSourceRecord) and isinstance(
        source.state,
        PdfDocumentState,
    ):
        return FileArtifact(path=source_path, mime_type="application/pdf")

    return FileArtifact(path=source_path, mime_type=source.file.mime_type)


def get_document_text_lines(session_id: str) -> list[PdfTextLine]:
    """Return all page-aware text evidence for a native or converted PDF."""
    session = session_store.require_session(session_id)
    source = session.source
    if not isinstance(source, DocumentSourceRecord) or not isinstance(
        source.state,
        (PdfDocumentState, DocxDocumentState),
    ):
        raise app_error(ErrorCode.NOT_PDF_SESSION)
    return source_store.get_pdf_lines(session_id)


async def get_docx_picture_placements(session_id: str) -> tuple[DocxPicturePlacement, ...]:
    """Return placements derived from the current rendered DOCX preview."""
    session = session_store.require_session(session_id)
    source = session.source
    if not isinstance(source, DocumentSourceRecord) or not isinstance(
        source.state,
        DocxDocumentState,
    ):
        raise app_error(
            ErrorCode.INVALID_DOCX_TEXT_TARGET,
            details={"reason": "source_format_mismatch"},
        )
    return await get_picture_placements(
        session_id,
        source,
        review_store.get_layers(session_id, []),
    )


def resolve_docx_text_target(
    session_id: str,
    *,
    page: int,
    line_id: str,
    exact_text: str,
) -> DocxTextLocator:
    """Resolve text selected in the converted PDF to an Open XML source range."""
    session = session_store.require_session(session_id)
    source = session.source
    if not isinstance(source, DocumentSourceRecord) or not isinstance(
        source.state,
        DocxDocumentState,
    ):
        raise app_error(
            ErrorCode.INVALID_DOCX_TEXT_TARGET,
            details={"reason": "source_format_mismatch"},
        )
    locator = resolve_pdf_selection(
        source_store.get_docx_blocks(session_id),
        source_store.get_pdf_lines(session_id),
        page=page,
        line_id=line_id,
        exact_text=exact_text,
        source_sha256=source.file.sha256,
    )
    if locator is None:
        raise app_error(
            ErrorCode.INVALID_DOCX_TEXT_TARGET,
            details={"reason": "selection_is_missing_or_ambiguous"},
        )
    return locator
