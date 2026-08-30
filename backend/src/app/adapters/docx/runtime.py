"""Application-scoped DOCX processor access."""

from __future__ import annotations

import asyncio
import platform
from pathlib import Path

from app.adapters.docx.contracts import (
    DocxImageReplacement,
    DocxInspectResult,
    DocxProcessorOperation,
    DocxRenderLayer,
    DocxRenderResult,
)
from app.adapters.docx.pool import DocxProcessorPool
from app.core.config import DOCX_WORKERS
from app.core.paths import data_root, project_root
from app.errors import ErrorCode, app_error

_pool: DocxProcessorPool | None = None
_pool_lock = asyncio.Lock()
_development: bool | None = None


def configure_runtime(*, development: bool) -> None:
    global _development

    if _pool is not None:
        raise RuntimeError("DOCX runtime cannot be reconfigured after the processor pool starts.")

    _development = development


def _runtime_id() -> str:
    systems = {"Linux": "linux", "Windows": "win", "Darwin": "osx"}
    machines = {
        "x86_64": "x64",
        "AMD64": "x64",
        "aarch64": "arm64",
        "ARM64": "arm64",
        "arm64": "arm64",
    }
    try:
        return f"{systems[platform.system()]}-{machines[platform.machine()]}"
    except KeyError as exc:
        raise app_error(ErrorCode.DOCX_PROCESSOR_MISSING) from exc


def _processor_path() -> Path:
    if _development is None:
        raise RuntimeError("DOCX runtime has not been configured.")

    executable = "aiadr-docx.exe" if platform.system() == "Windows" else "aiadr-docx"

    if _development:
        processor = project_root() / "docx-processor" / "bin" / "Debug" / "net10.0" / executable
        missing_message = (
            "The development DOCX processor is missing. "
            "Run `dotnet build docx-processor/Aiadr.Docx.csproj`."
        )
    else:
        processor = (
            project_root()
            / "docx-processor"
            / "bin"
            / "Release"
            / "net10.0"
            / _runtime_id()
            / "publish"
            / executable
        )
        missing_message = (
            "The published DOCX processor is missing. "
            "Run `uv run python scripts/publish_docx_processor.py`."
        )

    if not processor.is_file():
        raise app_error(ErrorCode.DOCX_PROCESSOR_MISSING, message=missing_message)

    return processor


async def _get_pool() -> DocxProcessorPool:
    global _pool
    async with _pool_lock:
        if _pool is None:
            pool = DocxProcessorPool(_processor_path(), DOCX_WORKERS)
            await pool.start()
            _pool = pool
        return _pool


async def close_runtime() -> None:
    global _pool
    async with _pool_lock:
        pool = _pool
        _pool = None
    if pool is not None:
        await pool.close()


def _common_payload(
    source_path: Path,
    output_path: Path,
    source_sha256: str,
) -> dict[str, object]:
    root = str(data_root().resolve())
    return {
        "source_path": str(source_path.resolve()),
        "expected_source_sha256": source_sha256,
        "output_path": str(output_path.resolve()),
        "allowed_roots": [root],
    }


async def inspect_docx(
    source_path: Path,
    output_path: Path,
    image_output_directory: Path,
    *,
    source_sha256: str,
) -> DocxInspectResult:
    pool = await _get_pool()
    payload = _common_payload(source_path, output_path, source_sha256)
    payload["image_output_directory"] = str(image_output_directory.resolve())
    response = await pool.execute(DocxProcessorOperation.INSPECT, payload, timeout=30.0)
    return DocxInspectResult.model_validate(response.payload)


async def render_docx(
    source_path: Path,
    output_path: Path,
    *,
    source_sha256: str,
    layers: tuple[DocxRenderLayer, ...],
    image_replacements: tuple[DocxImageReplacement, ...],
) -> DocxRenderResult:
    pool = await _get_pool()
    payload = _common_payload(source_path, output_path, source_sha256)
    payload["layers"] = [layer.model_dump(mode="json") for layer in layers]
    payload["image_replacements"] = [
        replacement.model_dump(mode="json") for replacement in image_replacements
    ]
    response = await pool.execute(DocxProcessorOperation.RENDER, payload, timeout=45.0)
    return DocxRenderResult.model_validate(response.payload)
