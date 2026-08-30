"""HTTP routes for file uploads."""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, status

from app.operations.upload import create_session_from_upload

router = APIRouter(tags=["uploads"])


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def request_upload_file(
    file: UploadFile,
) -> str:
    """Upload a sample file and create a review session."""
    session = await create_session_from_upload(
        stream=file.file,
        filename=file.filename or "upload",
        mime_type=file.content_type or "application/octet-stream",
    )
    return session.session_id
