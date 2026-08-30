"""Cross-platform LibreOffice conversion boundary."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from app.core.config import LIBREOFFICE_PATH
from app.errors import ErrorCode, app_error
from pydantic import BaseModel

CONVERSION_TIMEOUT_SECONDS = 120
STATUS_TIMEOUT_SECONDS = 10
PDF_EXPORT_FILTER = (
    'pdf:writer_pdf_Export:'
    '{"UseLosslessCompression":{"type":"boolean","value":"true"},'
    '"ReduceImageResolution":{"type":"boolean","value":"false"}}'
)


class LibreOfficeStatus(BaseModel):
    """Runtime LibreOffice availability status."""

    available: bool
    path: str | None = None
    version: str | None = None
    error: str | None = None


def _standard_locations() -> tuple[Path, ...]:
    system = platform.system()
    if system == "Darwin":
        return (Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),)
    if system == "Windows":
        roots = (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"))
        return tuple(
            Path(root) / "LibreOffice" / "program" / "soffice.com" for root in roots if root
        )
    return ()


def find_executable() -> Path | None:
    """Find the configured, PATH-provided, or standard LibreOffice executable."""
    if LIBREOFFICE_PATH:
        configured = Path(LIBREOFFICE_PATH).expanduser()
        return configured if configured.is_file() else None

    for name in ("soffice", "libreoffice"):
        if executable := shutil.which(name):
            return Path(executable)
    for candidate in _standard_locations():
        if candidate.is_file():
            return candidate
    return None


def require_executable() -> Path:
    """Return the LibreOffice executable or raise the shared dependency error."""
    if executable := find_executable():
        return executable
    raise app_error(ErrorCode.DOCUMENT_CONVERTER_MISSING)


def libreoffice_status() -> LibreOfficeStatus:
    """Check whether LibreOffice can be executed."""
    executable = find_executable()
    if executable is None:
        message = (
            "The configured LibreOffice executable was not found."
            if LIBREOFFICE_PATH
            else "LibreOffice was not found on PATH or in a standard installation location."
        )
        return LibreOfficeStatus(available=False, error=message)
    detected_path = str(executable.resolve())
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=STATUS_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return LibreOfficeStatus(
            available=False,
            path=detected_path,
            error="LibreOffice availability check timed out.",
        )
    except OSError:
        return LibreOfficeStatus(
            available=False,
            path=detected_path,
            error="LibreOffice could not be executed.",
        )
    version = next(
        (line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()),
        None,
    )
    return LibreOfficeStatus(
        available=result.returncode == 0,
        path=detected_path,
        version=version,
        error=None
        if result.returncode == 0
        else f"LibreOffice exited with status {result.returncode}.",
    )


def convert_docx_to_pdf(source: Path, destination: Path) -> None:
    """Convert one DOCX into one PDF using an isolated LibreOffice profile."""
    executable = require_executable()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".libreoffice-", dir=destination.parent) as directory:
        workspace = Path(directory)
        input_path = workspace / "source.docx"
        output_path = workspace / "source.pdf"
        profile = workspace / "profile"
        profile.mkdir()
        shutil.copyfile(source, input_path)
        command = (
            str(executable),
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to",
            PDF_EXPORT_FILTER,
            "--outdir",
            str(workspace),
            str(input_path),
        )
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=CONVERSION_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise app_error(ErrorCode.DOCUMENT_CONVERSION_FAILED) from exc
        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            raise app_error(
                ErrorCode.DOCUMENT_CONVERSION_FAILED,
                details={"return_code": result.returncode},
            )
        with NamedTemporaryFile(
            prefix=f".{destination.stem}-",
            suffix=".pdf.tmp",
            dir=destination.parent,
            delete=False,
        ) as file:
            temporary = Path(file.name)
        try:
            shutil.copyfile(output_path, temporary)
            temporary.replace(destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
