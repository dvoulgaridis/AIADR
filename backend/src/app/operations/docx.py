"""Open XML rendering and PDF preview operations for DOCX sources."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

from PIL import Image
from pydantic import BaseModel

from app.adapters.docx import (
    DocxImageReplacement,
    DocxRenderLayer,
    inspect_docx,
    render_docx,
)
from app.adapters.libreoffice import convert_docx_to_pdf
from app.core.paths import prepared_dir
from app.domain.finding import (
    DocumentTarget,
    DocxPictureSurface,
    DocxTextLocator,
    ImageTarget,
    ReviewDecision,
    TargetRegion,
)
from app.domain.layer import Layer, LayerAction
from app.errors import ErrorCode, app_error
from app.files.hashing import sha256_file
from app.files.records import StoredFile
from app.preprocessing.docx_images import normalize_docx_images
from app.preprocessing.docx_placements import project_docx_picture_placements
from app.preprocessing.pdf import extract_pdf_text_index
from app.redaction.image_renderer import (
    apply_image_effects,
    image_layers_for_surface,
)
from app.redaction.text_replacements import resolve_text_replacements
from app.sources.docx_images import (
    DocxImageOccurrence,
    DocxPicturePlacement,
)
from app.sources.docx_text import DocxTextBlock
from app.sources.pdf_text import PdfTextLine
from app.sources.records import DocumentSourceRecord, DocxDocumentState
from app.storage import source_store
from app.storage.file_store import preview_path, require_docx_image_asset, require_source_path

DOCX_RENDER_REVISION = 1


class DocxImageRenderLayer(BaseModel):
    """Canonical picture-layer state included in the DOCX render fingerprint."""

    layer_id: str
    occurrence_id: str
    region: TargetRegion
    action: str
    effect: str
    fill_color: str

    model_config = {"extra": "forbid", "frozen": True}


class DocxRenderRequest(BaseModel):
    """Values whose changes can alter rendered DOCX bytes."""

    source_sha256: str
    layers: tuple[DocxRenderLayer, ...]
    image_layers: tuple[DocxImageRenderLayer, ...]

    model_config = {"extra": "forbid", "frozen": True}


@dataclass(frozen=True, slots=True)
class RenderedDocx:
    path: Path
    sha256: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class DocxPreviewEvidence:
    page_count: int
    text_lines: tuple[PdfTextLine, ...]


@dataclass(frozen=True, slots=True)
class DocxInspection:
    source: DocumentSourceRecord
    text_blocks: tuple[DocxTextBlock, ...]
    preview_lines: tuple[PdfTextLine, ...]
    image_occurrences: tuple[DocxImageOccurrence, ...]


@dataclass(slots=True)
class _BuildLock:
    lock: asyncio.Lock
    users: int = 0


_build_locks: dict[str, _BuildLock] = {}
_build_locks_guard = asyncio.Lock()


@asynccontextmanager
async def _serialize_build(key: str) -> AsyncGenerator[None, None]:
    """Coalesce preview builds for one session without retaining session state."""
    async with _build_locks_guard:
        entry = _build_locks.setdefault(key, _BuildLock(asyncio.Lock()))
        entry.users += 1
    await entry.lock.acquire()
    try:
        yield
    finally:
        entry.lock.release()
        async with _build_locks_guard:
            entry.users -= 1
            if entry.users == 0:
                _build_locks.pop(key, None)


def render_layers(layers: list[Layer]) -> tuple[DocxRenderLayer, ...]:
    """Select and normalize layers that alter DOCX bytes."""
    replacements = resolve_text_replacements(layers)
    selected: list[DocxRenderLayer] = []
    for layer in layers:
        target = layer.finding.target
        replacement = replacements.get(layer.id)
        if replacement is None or not isinstance(target, DocumentTarget):
            continue
        if not isinstance(target.locator, DocxTextLocator):
            continue
        selected.append(
            DocxRenderLayer(
                layer_id=layer.id,
                target=target.locator,
                replacement_text=replacement,
            )
        )
    return tuple(sorted(selected, key=lambda item: item.layer_id))


def image_render_layers(layers: list[Layer]) -> tuple[DocxImageRenderLayer, ...]:
    """Select DOCX picture layers and normalize their fingerprint state."""
    selected: list[DocxImageRenderLayer] = []
    for layer in layers:
        target = layer.finding.target
        if (
            layer.finding.review_decision is not ReviewDecision.CONFIRMED
            or not layer.enabled
            or layer.action is LayerAction.PRESERVE
            or not isinstance(target, ImageTarget)
            or not isinstance(target.surface, DocxPictureSurface)
        ):
            continue
        surface = target.surface
        selected.append(
            DocxImageRenderLayer(
                layer_id=layer.id,
                occurrence_id=surface.occurrence_id,
                region=target.region,
                action=layer.action,
                effect=layer.effect,
                fill_color=layer.fill_color,
            )
        )
    return tuple(sorted(selected, key=lambda item: item.layer_id))


def _docx_state(source: DocumentSourceRecord) -> DocxDocumentState:
    if not isinstance(source.state, DocxDocumentState):
        raise TypeError("DOCX operation requires word-processing document state")
    return source.state


def _request(source: DocumentSourceRecord, layers: list[Layer]) -> DocxRenderRequest:
    _docx_state(source)
    return DocxRenderRequest(
        source_sha256=source.file.sha256,
        layers=render_layers(layers),
        image_layers=image_render_layers(layers),
    )


def _fingerprint(request: DocxRenderRequest) -> str:
    canonical = json.dumps(
        {
            "renderer_revision": DOCX_RENDER_REVISION,
            "request": request.model_dump(mode="json"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _temporary_docx(session_id: str) -> Path:
    directory = preview_path(session_id, "placeholder").parent
    with NamedTemporaryFile(prefix=".docx-", suffix=".tmp", dir=directory, delete=False) as file:
        return Path(file.name)


def _docx_path(session_id: str, fingerprint: str) -> Path:
    return preview_path(session_id, f"{fingerprint}.docx")


def _pdf_path(session_id: str, fingerprint: str) -> Path:
    return preview_path(session_id, f"{fingerprint}.pdf")


def _placements_path(session_id: str, fingerprint: str) -> Path:
    return preview_path(session_id, f"{fingerprint}.placements.json")


async def _publish_docx(
    session_id: str,
    temporary: Path,
    fingerprint: str,
    expected_sha256: str,
) -> RenderedDocx:
    sha256 = await asyncio.to_thread(sha256_file, temporary)
    if sha256 != expected_sha256:
        raise ValueError("DOCX output hash does not match processor result")
    target = _docx_path(session_id, fingerprint)
    if target.exists():
        temporary.unlink()
    else:
        temporary.replace(target)
    return RenderedDocx(
        path=target,
        sha256=sha256,
        fingerprint=fingerprint,
    )


async def _cached_docx(session_id: str, fingerprint: str) -> RenderedDocx | None:
    path = _docx_path(session_id, fingerprint)
    if not path.is_file():
        return None
    sha256 = await asyncio.to_thread(sha256_file, path)
    return RenderedDocx(
        path=path,
        sha256=sha256,
        fingerprint=fingerprint,
    )


def _prune_previews(session_id: str, keep: int = 3) -> None:
    directory = preview_path(session_id, "placeholder").parent
    documents = sorted(
        directory.glob("*.docx"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    retained = {path.stem for path in documents[:keep]}
    for path in documents[keep:]:
        path.unlink(missing_ok=True)
        _placements_path(session_id, path.stem).unlink(missing_ok=True)
    for path in directory.glob("*.pdf"):
        if path.stem not in retained:
            path.unlink(missing_ok=True)
    for path in directory.glob("*.placements.json"):
        fingerprint = path.name.removesuffix(".placements.json")
        if fingerprint not in retained:
            path.unlink(missing_ok=True)


async def inspect_source(
    session_id: str,
    file: StoredFile,
) -> DocxInspection:
    """Inspect a DOCX and build its canonical text and PDF preview evidence."""
    source = DocumentSourceRecord(
        file=file,
        state=DocxDocumentState(
            block_count=0,
            character_count=0,
            page_count=1,
        ),
    )
    fingerprint = _fingerprint(_request(source, []))
    inspection_temporary = _temporary_docx(session_id)
    document_temporary = _temporary_docx(session_id)
    try:
        with TemporaryDirectory(
            prefix=".docx-source-images-",
            dir=prepared_dir(session_id),
        ) as raw:
            result = await inspect_docx(
                require_source_path(session_id, source.file),
                inspection_temporary,
                Path(raw),
                source_sha256=source.file.sha256,
            )
            occurrences = await asyncio.to_thread(
                normalize_docx_images,
                session_id,
                Path(raw),
                result.image_occurrences,
            )
        if await asyncio.to_thread(sha256_file, inspection_temporary) != result.document_sha256:
            raise ValueError("DOCX inspection output hash does not match processor result")
        with TemporaryDirectory(
            prefix=".docx-replacements-",
            dir=preview_path(session_id, "placeholder").parent,
        ) as replacement_directory:
            replacements = await asyncio.to_thread(
                _build_image_replacements,
                session_id,
                [],
                list(occurrences),
                Path(replacement_directory),
            )
            rendered_result = await render_docx(
                require_source_path(session_id, source.file),
                document_temporary,
                source_sha256=source.file.sha256,
                layers=(),
                image_replacements=replacements,
            )
        rendered = await _publish_docx(
            session_id,
            document_temporary,
            fingerprint,
            rendered_result.document_sha256,
        )
        inspection_temporary.unlink(missing_ok=True)
        pdf_path = await _ensure_preview_pdf(
            session_id,
            rendered,
        )
        await _ensure_picture_placements(
            session_id,
            rendered,
            pdf_path,
            occurrences,
            [],
        )
        preview = await _inspect_preview_evidence(pdf_path)
        updated = source.model_copy(
            update={
                "state": DocxDocumentState(
                    block_count=len(result.blocks),
                    character_count=result.character_count,
                    page_count=preview.page_count,
                    targetable_image_count=sum(item.targetable for item in occurrences),
                    unsupported_image_count=sum(not item.targetable for item in occurrences),
                ),
            }
        )
        _prune_previews(session_id)
        return DocxInspection(
            source=updated,
            text_blocks=result.blocks,
            preview_lines=preview.text_lines,
            image_occurrences=occurrences,
        )
    except BaseException:
        inspection_temporary.unlink(missing_ok=True)
        document_temporary.unlink(missing_ok=True)
        raise


async def get_rendered_docx(
    session_id: str,
    source: DocumentSourceRecord,
    layers: list[Layer],
) -> RenderedDocx:
    """Return the Open XML-rendered document for the current effect state."""
    request = _request(source, layers)
    fingerprint = _fingerprint(request)
    if cached := await _cached_docx(session_id, fingerprint):
        return cached

    async with _serialize_build(session_id):
        if cached := await _cached_docx(session_id, fingerprint):
            return cached
        document_temporary = _temporary_docx(session_id)
        try:
            with TemporaryDirectory(
                prefix=".docx-replacements-",
                dir=preview_path(session_id, "placeholder").parent,
            ) as replacement_directory:
                replacements = await asyncio.to_thread(
                    _build_image_replacements,
                    session_id,
                    layers,
                    source_store.get_docx_image_occurrences(session_id),
                    Path(replacement_directory),
                )
                result = await render_docx(
                    require_source_path(session_id, source.file),
                    document_temporary,
                    source_sha256=source.file.sha256,
                    layers=request.layers,
                    image_replacements=replacements,
                )
            rendered = await _publish_docx(
                session_id,
                document_temporary,
                fingerprint,
                result.document_sha256,
            )
            _prune_previews(session_id)
            return rendered
        except BaseException:
            document_temporary.unlink(missing_ok=True)
            raise


def _build_image_replacements(
    session_id: str,
    layers: list[Layer],
    occurrences: list[DocxImageOccurrence],
    output_directory: Path,
) -> tuple[DocxImageReplacement, ...]:
    """Render one deterministic replacement bitmap per targetable occurrence."""
    known = {occurrence.occurrence_id: occurrence for occurrence in occurrences}
    requested = {
        layer.finding.target.surface.occurrence_id
        for layer in layers
        if isinstance(layer.finding.target, ImageTarget)
        and isinstance(layer.finding.target.surface, DocxPictureSurface)
    }
    if requested - known.keys():
        raise ValueError("A DOCX picture layer references an unknown occurrence")

    replacements: list[DocxImageReplacement] = []
    for occurrence in sorted(occurrences, key=lambda item: item.ordinal):
        occurrence_layers = image_layers_for_surface(
            layers,
            DocxPictureSurface(occurrence_id=occurrence.occurrence_id),
        )
        if (
            not occurrence.targetable
            or occurrence.asset_filename is None
            or occurrence.normalized_sha256 is None
        ):
            if occurrence_layers:
                raise ValueError("A DOCX picture layer references an unsupported occurrence")
            continue
        source = require_docx_image_asset(
            session_id,
            occurrence.asset_filename,
            occurrence.normalized_sha256,
        )
        with Image.open(source) as image:
            rendered = apply_image_effects(image, occurrence_layers)
        destination = output_directory / f"{occurrence.occurrence_id}.png"
        try:
            rendered.save(destination, format="PNG", compress_level=9, optimize=False)
        finally:
            rendered.close()
        replacements.append(
            DocxImageReplacement(
                occurrence_id=occurrence.occurrence_id,
                replacement_path=str(destination),
                replacement_sha256=sha256_file(destination),
            )
        )
    return tuple(replacements)


def _load_placements(path: Path) -> tuple[DocxPicturePlacement, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("DOCX picture placement cache is invalid")
    placements = tuple(DocxPicturePlacement.model_validate(item) for item in payload)
    if len({item.occurrence_id for item in placements}) != len(placements):
        raise ValueError("DOCX picture placement cache contains duplicate occurrences")
    return placements


def _publish_placements(path: Path, placements: tuple[DocxPicturePlacement, ...]) -> None:
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(
                [item.model_dump(mode="json") for item in placements],
                file,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        temporary.replace(path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


async def _ensure_preview_pdf(
    session_id: str,
    document: RenderedDocx,
) -> Path:
    target = _pdf_path(session_id, document.fingerprint)
    if not target.is_file():
        async with _serialize_build(f"{session_id}:pdf:{document.fingerprint}"):
            if not target.is_file():
                await asyncio.to_thread(convert_docx_to_pdf, document.path, target)
    return target


async def _ensure_picture_placements(
    session_id: str,
    document: RenderedDocx,
    pdf_path: Path,
    occurrences: tuple[DocxImageOccurrence, ...],
    layers: list[Layer],
) -> Path:
    placement_cache = _placements_path(session_id, document.fingerprint)
    if not placement_cache.is_file():
        async with _serialize_build(f"{session_id}:pdf:{document.fingerprint}"):
            if not placement_cache.is_file():
                try:
                    placements = await asyncio.to_thread(
                        project_docx_picture_placements,
                        session_id,
                        pdf_path,
                        occurrences,
                        layers,
                    )
                except ValueError as exc:
                    raise app_error(ErrorCode.DOCX_PROCESSING_FAILED) from exc
                await asyncio.to_thread(
                    _publish_placements,
                    placement_cache,
                    placements,
                )
    return placement_cache


async def get_preview_path(
    session_id: str,
    source: DocumentSourceRecord,
    layers: list[Layer],
) -> Path:
    """Return the PDF converted from the exact DOCX document under review."""
    rendered = await get_rendered_docx(session_id, source, layers)
    return await _ensure_preview_pdf(session_id, rendered)


async def get_picture_placements(
    session_id: str,
    source: DocumentSourceRecord,
    layers: list[Layer],
) -> tuple[DocxPicturePlacement, ...]:
    """Return picture placements for the current rendered DOCX fingerprint."""
    rendered = await get_rendered_docx(session_id, source, layers)
    pdf_path = await _ensure_preview_pdf(session_id, rendered)
    placements_path = await _ensure_picture_placements(
        session_id,
        rendered,
        pdf_path,
        tuple(source_store.get_docx_image_occurrences(session_id)),
        layers,
    )
    return await asyncio.to_thread(_load_placements, placements_path)


async def _inspect_preview_evidence(
    pdf_path: Path,
) -> DocxPreviewEvidence:
    index = await asyncio.to_thread(extract_pdf_text_index, pdf_path)
    return DocxPreviewEvidence(
        page_count=index.page_count,
        text_lines=index.lines,
    )


async def render_output(
    session_id: str,
    source: DocumentSourceRecord,
    layers: list[Layer],
    destination: Path,
) -> None:
    """Promote the same Open XML-rendered DOCX shown through PDF preview."""
    rendered = await get_rendered_docx(session_id, source, layers)
    await asyncio.to_thread(shutil.copyfile, rendered.path, destination)
    if await asyncio.to_thread(sha256_file, destination) != rendered.sha256:
        destination.unlink(missing_ok=True)
        raise ValueError("DOCX output hash does not match previewed document")
