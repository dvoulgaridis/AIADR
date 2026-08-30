"""API routes for uploaded sources and browser previews."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.contracts import (
    DocumentTextLinesResponse,
    DocxPicturePlacement,
    DocxPicturePlacementsResponse,
    DocxTextLocator,
    DocxTextSelectionRequest,
    PdfTextLine,
)
from app.operations import source as source_operations

router = APIRouter(tags=["sources"])


def _file_response(
    artifact: source_operations.FileArtifact,
) -> FileResponse:
    background = (
        BackgroundTask(artifact.path.unlink, missing_ok=True)
        if artifact.delete_after_send
        else None
    )
    return FileResponse(
        artifact.path,
        media_type=artifact.mime_type,
        filename=artifact.filename,
        background=background,
    )


@router.get("/sessions/{session_id}/source")
async def download_source(session_id: str) -> FileResponse:
    """Return the uploaded source file."""
    return _file_response(source_operations.get_uploaded_source(session_id))


@router.get("/sessions/{session_id}/preview")
async def preview_source(session_id: str) -> FileResponse:
    """Return a browser-friendly source preview."""
    return _file_response(await source_operations.get_source_preview(session_id))


@router.get("/sessions/{session_id}/document/text-lines")
async def get_document_text_lines(session_id: str) -> DocumentTextLinesResponse:
    """Return text lines from every PDF page displayed for this document session."""
    lines = [
        PdfTextLine.model_validate(line.model_dump())
        for line in source_operations.get_document_text_lines(session_id)
    ]
    return DocumentTextLinesResponse(session_id=session_id, lines=lines)


@router.get("/sessions/{session_id}/document/docx/picture-placements")
async def get_docx_picture_placements(session_id: str) -> DocxPicturePlacementsResponse:
    """Return picture placements for the current rendered DOCX preview."""
    placements = [
        DocxPicturePlacement.model_validate(item.model_dump(mode="json"))
        for item in await source_operations.get_docx_picture_placements(session_id)
    ]
    return DocxPicturePlacementsResponse(placements=placements)


@router.post("/sessions/{session_id}/document/docx/target")
async def resolve_docx_text_target(
    session_id: str,
    request: DocxTextSelectionRequest,
) -> DocxTextLocator:
    """Resolve converted-PDF text evidence to a canonical Open XML target."""
    locator = source_operations.resolve_docx_text_target(
        session_id,
        page=request.page,
        line_id=request.line_id,
        exact_text=request.exact_text,
    )
    return DocxTextLocator.model_validate(locator.model_dump(mode="json"))
