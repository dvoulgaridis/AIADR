"""API routes for audit export."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.contracts import ExportCreateResponse
from app.errors import ErrorCode, app_error
from app.operations.export import (
    create_export_bundle,
    get_latest_export_bundle,
)
from app.storage import file_store, session_store

router = APIRouter(tags=["exports"])


@router.post("/sessions/{session_id}/export")
async def request_create_export_bundle(session_id: str) -> ExportCreateResponse:
    """Create an audit export bundle for the session."""
    bundle = await create_export_bundle(session_id)
    return ExportCreateResponse(
        session_id=session_id,
        status="created",
        filename=bundle.filename,
    )


@router.get("/sessions/{session_id}/output")
async def download_output(session_id: str) -> FileResponse:
    """Download the redacted output file."""
    session = session_store.require_session(session_id)
    rendered = session.rendered_file
    if rendered is None:
        raise app_error(ErrorCode.OUTPUT_MISSING, details={"session_id": session_id})
    path = file_store.require_rendered_path(session_id, rendered)
    return FileResponse(
        path,
        filename=rendered.filename,
        media_type=rendered.mime_type,
    )


@router.get("/sessions/{session_id}/export/latest")
async def download_latest_export_bundle(session_id: str) -> FileResponse:
    """Download the latest audit export bundle for the session."""
    path, filename = get_latest_export_bundle(session_id)
    return FileResponse(path, filename=filename, media_type="application/zip")
