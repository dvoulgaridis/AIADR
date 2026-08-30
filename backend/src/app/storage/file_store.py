"""Local file storage with bounded streaming and safe path resolution."""

from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import MAX_UPLOAD_MB
from app.core.paths import (
    data_root,
    exports_dir,
    outputs_dir,
    prepared_dir,
    previews_dir,
    uploads_dir,
)
from app.errors import ErrorCode, app_error
from app.files.hashing import sha256_file
from app.files.records import StoredFile
from app.sources.formats import canonical_mime_type, resolve_upload_format

_CHUNK_SIZE = 1024 * 1024
_MANAGED_RUNTIME_AREAS = ("uploads", "outputs", "exports", "prepared", "previews")


@dataclass(frozen=True, slots=True)
class FinalizedFile:
    """A durable file and whether this finalization created its path."""

    file: StoredFile
    created: bool


def safe_filename(filename: str) -> str:
    """Return a conservative basename for internal filesystem use."""
    base = Path(filename).name.strip() or "upload"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return safe[:120] or "upload"


def normalized_filename(filename: str) -> str:
    """Return a non-empty user-visible basename."""
    return Path(filename).name.strip() or "upload"


def ensure_within_data_root(path: Path) -> Path:
    """Resolve a path and ensure it stays under the configured data root."""
    root = data_root().resolve()
    resolved = path.resolve()
    if root not in resolved.parents and resolved != root:
        raise app_error(ErrorCode.UNSAFE_PATH)
    return resolved


def _require_safe_stored_filename(stored_filename: str) -> None:
    if Path(stored_filename).name != stored_filename:
        raise app_error(ErrorCode.UNSAFE_PATH)


def save_upload(
    session_id: str,
    stream: BinaryIO,
    *,
    filename: str,
    mime_type: str,
) -> StoredFile:
    """Stream one caller-owned upload into finalized managed storage."""
    public_filename = normalized_filename(filename)
    file_format = resolve_upload_format(public_filename, mime_type)
    directory = uploads_dir(session_id)
    temporary = ensure_within_data_root(directory / ".upload.tmp")
    temporary.unlink(missing_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024

    try:
        with temporary.open("wb") as destination:
            while chunk := stream.read(_CHUNK_SIZE):
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise app_error(
                        ErrorCode.FILE_TOO_LARGE,
                        details={
                            "max_megabytes": MAX_UPLOAD_MB,
                            "size_bytes": size_bytes,
                        },
                    )
                digest.update(chunk)
                destination.write(chunk)

        sha256 = digest.hexdigest()
        stored_filename = f"{sha256}-{safe_filename(public_filename)}"
        target = ensure_within_data_root(directory / stored_filename)
        temporary.replace(target)
        return StoredFile(
            filename=public_filename,
            stored_filename=stored_filename,
            format=file_format,
            mime_type=canonical_mime_type(file_format),
            size_bytes=size_bytes,
            sha256=sha256,
        )
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def require_source_path(session_id: str, file: StoredFile) -> Path:
    """Return the existing path for a persisted uploaded source."""
    _require_safe_stored_filename(file.stored_filename)
    path = ensure_within_data_root(uploads_dir(session_id) / file.stored_filename)
    if path.is_file():
        return path
    raise app_error(
        ErrorCode.SESSION_FILE_MISSING,
        details={"session_id": session_id},
    )


def require_rendered_path(session_id: str, file: StoredFile) -> Path:
    """Return the existing path for a persisted rendered output."""
    _require_safe_stored_filename(file.stored_filename)
    path = ensure_within_data_root(outputs_dir(session_id) / file.stored_filename)
    if path.is_file():
        return path
    raise app_error(ErrorCode.OUTPUT_MISSING, details={"session_id": session_id})


def output_path(session_id: str, filename: str) -> Path:
    """Return a safe path for a working output or preview file."""
    return ensure_within_data_root(outputs_dir(session_id) / safe_filename(filename))


def preview_path(session_id: str, filename: str) -> Path:
    """Return a safe path inside one session's derived preview cache."""
    return ensure_within_data_root(previews_dir(session_id) / safe_filename(filename))


def docx_image_asset_path(session_id: str, filename: str) -> Path:
    """Return a safe path for one normalized DOCX picture asset."""
    return ensure_within_data_root(
        prepared_dir(session_id) / "docx-images" / safe_filename(filename)
    )


def require_docx_image_asset(session_id: str, filename: str, sha256: str) -> Path:
    """Return one persisted normalized DOCX picture after integrity validation."""
    _require_safe_stored_filename(filename)
    path = docx_image_asset_path(session_id, filename)
    if path.is_file() and sha256_file(path) == sha256:
        return path
    raise app_error(
        ErrorCode.SOURCE_INTEGRITY_ERROR,
        details={"session_id": session_id, "asset_filename": filename},
    )


def finalize_output(
    session_id: str,
    temporary: Path,
    *,
    filename: str,
    file_format: str,
    mime_type: str,
) -> FinalizedFile:
    """Move a completed output into immutable content-addressed storage."""
    temporary = ensure_within_data_root(temporary)
    sha256 = sha256_file(temporary)
    stored_filename = f"{sha256}-{safe_filename(filename)}"
    target = ensure_within_data_root(outputs_dir(session_id) / stored_filename)
    created = not target.exists()
    file = StoredFile(
        filename=normalized_filename(filename),
        stored_filename=stored_filename,
        format=file_format,
        mime_type=mime_type,
        size_bytes=(temporary if created else target).stat().st_size,
        sha256=sha256,
    )
    if created:
        temporary.replace(target)
    else:
        temporary.unlink()
    return FinalizedFile(
        file=file,
        created=created,
    )


def finalize_export(
    session_id: str,
    temporary: Path,
    *,
    export_id: str,
    filename: str,
) -> StoredFile:
    """Move a completed ZIP into immutable portable export storage."""
    temporary = ensure_within_data_root(temporary)
    sha256 = sha256_file(temporary)
    stored_filename = f"{safe_filename(export_id)}-{sha256}-{safe_filename(filename)}"
    target = export_path(session_id, stored_filename)
    temporary.replace(target)
    return StoredFile(
        filename=normalized_filename(filename),
        stored_filename=stored_filename,
        format="zip",
        mime_type="application/zip",
        size_bytes=target.stat().st_size,
        sha256=sha256,
    )


def export_path(session_id: str, stored_filename: str) -> Path:
    """Return a safe path for a new export file."""
    _require_safe_stored_filename(stored_filename)
    return ensure_within_data_root(exports_dir(session_id) / stored_filename)


def require_export_path(session_id: str, stored_filename: str) -> Path:
    """Return an existing safe export bundle path."""
    path = export_path(session_id, stored_filename)
    if path.is_file():
        return path
    raise app_error(ErrorCode.EXPORT_MISSING, details={"session_id": session_id})


def purge_session_files(session_id: str) -> None:
    """Idempotently remove all filesystem state owned by one session."""
    root = data_root()
    for area in _MANAGED_RUNTIME_AREAS:
        path = ensure_within_data_root(root / area / session_id)
        if path.exists():
            shutil.rmtree(path)


def managed_runtime_state_exists() -> bool:
    """Return whether managed session files exist without modifying them."""
    root = data_root()
    return any(
        path.is_dir() and next(path.iterdir(), None) is not None
        for area in _MANAGED_RUNTIME_AREAS
        if (path := ensure_within_data_root(root / area)).exists()
    )
