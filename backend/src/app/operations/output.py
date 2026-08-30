"""Render and persist the current reviewed output for a session."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import assert_never

from app.adapters.pdf import render_raster_pdf
from app.audit.events import AuditEvent, AuditEventType
from app.core.paths import outputs_dir
from app.domain.finding import ReviewDecision
from app.domain.layer import Layer, LayerAction
from app.errors import ErrorCode, JsonValue, app_error
from app.files.descriptors import fingerprint_file
from app.files.records import StoredFile
from app.inference.model_log import ModelInteractionLog
from app.operations.docx import render_output as render_docx_output
from app.redaction.audio_renderer import render_redacted_audio, supported_output_suffix
from app.redaction.image_renderer import render_redacted_image
from app.redaction.text_renderer import render_redacted_text
from app.sources.formats import canonical_mime_type
from app.sources.records import (
    AudioSourceRecord,
    DocumentSourceRecord,
    DocxDocumentState,
    ImageSourceRecord,
    PdfDocumentState,
    SourceRecord,
    TextDocumentState,
)
from app.storage import (
    file_store,
    model_log_store,
    review_store,
    session_file_store,
    session_store,
)
from app.storage.transaction import transaction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutputSnapshot:
    """Coherent values captured by one successful output commit."""

    session_id: str
    file: StoredFile
    source: SourceRecord
    layers: tuple[Layer, ...]
    model_logs: tuple[ModelInteractionLog, ...]
    audit_boundary_hash: str


def _render_layers(layers: tuple[Layer, ...]) -> list[Layer]:
    return [
        layer
        for layer in layers
        if layer.finding.review_decision is ReviewDecision.CONFIRMED
        and layer.enabled
        and layer.action is not LayerAction.PRESERVE
    ]


def _temporary_output_path(session_id: str, file_format: str) -> Path:
    with NamedTemporaryFile(
        prefix=".output-",
        suffix=f".{file_format}",
        dir=outputs_dir(session_id),
        delete=False,
    ) as temporary:
        return Path(temporary.name)


def _destination(source: SourceRecord) -> tuple[str, str]:
    if isinstance(source, ImageSourceRecord):
        return "redacted.png", "png"
    if isinstance(source, DocumentSourceRecord):
        match source.state:
            case TextDocumentState():
                return f"redacted.{source.file.format}", source.file.format
            case PdfDocumentState():
                return "redacted.pdf", "pdf"
            case DocxDocumentState():
                return "redacted.docx", "docx"
            case unexpected_state:
                assert_never(unexpected_state)
    if isinstance(source, AudioSourceRecord):
        suffix = supported_output_suffix(f".{source.file.format}")
        return f"redacted{suffix}", suffix.removeprefix(".")
    assert_never(source)


async def _render(
    session_id: str,
    source: SourceRecord,
    source_path: Path,
    layers: list[Layer],
    destination: Path,
) -> None:
    if isinstance(source, ImageSourceRecord):
        await asyncio.to_thread(render_redacted_image, source_path, layers, destination)
        return
    if isinstance(source, AudioSourceRecord):
        await asyncio.to_thread(render_redacted_audio, source_path, layers, destination)
        return
    if isinstance(source, DocumentSourceRecord):
        state = source.state
        if isinstance(state, TextDocumentState):
            await asyncio.to_thread(render_redacted_text, source_path, layers, destination)
            return
        if isinstance(state, DocxDocumentState):
            await render_docx_output(session_id, source, layers, destination)
            return
        if not isinstance(state, PdfDocumentState):
            assert_never(state)
        await asyncio.to_thread(render_raster_pdf, source_path, layers, destination)
        return
    assert_never(source)


async def render_redacted_output(session_id: str) -> OutputSnapshot:
    """Render and commit a coherent reviewed-output snapshot."""
    session = session_store.require_session(session_id)
    source = session.source
    source_path = file_store.require_source_path(session_id, source.file)
    layers = tuple(review_store.get_layers(session_id, []))
    pending_finding_ids: list[JsonValue] = [
        layer.finding.id
        for layer in layers
        if layer.finding.review_decision is ReviewDecision.NEEDS_REVIEW
    ]
    if pending_finding_ids:
        raise app_error(
            ErrorCode.OUTPUT_BLOCKED_PENDING_REVIEW,
            details={
                "pending_count": len(pending_finding_ids),
                "pending_finding_ids": pending_finding_ids,
            },
        )

    render_layers = _render_layers(layers)
    filename, file_format = _destination(source)
    temporary = _temporary_output_path(session_id, file_format)
    finalized: file_store.FinalizedFile | None = None
    previous_rendered: StoredFile | None = None

    try:
        await _render(session_id, source, source_path, render_layers, temporary)
        finalized = file_store.finalize_output(
            session_id,
            temporary,
            filename=filename,
            file_format=file_format,
            mime_type=canonical_mime_type(file_format),
        )
        rendered = finalized.file
        with transaction() as tx:
            current_source = session_file_store.require_source_with_connection(
                tx.connection,
                session_id,
            )
            if current_source != source:
                raise app_error(
                    ErrorCode.OUTPUT_STATE_CHANGED,
                    details={"session_id": session_id, "component": "source"},
                )

            current_layers = tuple(
                review_store.get_layers_with_connection(
                    tx.connection,
                    session_id,
                    [],
                )
            )
            if current_layers != layers:
                raise app_error(
                    ErrorCode.OUTPUT_STATE_CHANGED,
                    details={"session_id": session_id, "component": "review"},
                )

            model_logs = tuple(
                model_log_store.get_logs_with_connection(
                    tx.connection,
                    session_id,
                )
            )
            previous_rendered = session_file_store.get_rendered_file_with_connection(
                tx.connection,
                session_id,
            )
            session_file_store.set_rendered_file_with_connection(
                tx.connection,
                session_id,
                current_source,
                rendered,
            )
            tx.record(
                AuditEvent(
                    session_id=session_id,
                    event_type=AuditEventType.OUTPUT_RENDERED,
                    payload={
                        "source_kind": current_source.kind,
                        "file": fingerprint_file(rendered).model_dump(mode="json"),
                    },
                )
            )
    except BaseException as error:
        if finalized is not None and finalized.created:
            try:
                file_store.output_path(
                    session_id,
                    finalized.file.stored_filename,
                ).unlink(missing_ok=True)
            except OSError as cleanup_error:
                error.add_note(
                    f"Rendered-output cleanup also failed: {cleanup_error!r}"
                )
        raise
    finally:
        temporary.unlink(missing_ok=True)

    if (
        len(tx.committed_events) != 1
        or tx.committed_events[0]["event_type"] != AuditEventType.OUTPUT_RENDERED
    ):
        raise RuntimeError("Output transaction must commit exactly one output.rendered event.")

    if (
        previous_rendered is not None
        and previous_rendered.stored_filename != rendered.stored_filename
    ):
        try:
            file_store.output_path(
                session_id,
                previous_rendered.stored_filename,
            ).unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "Superseded rendered-output cleanup failed session_id=%s",
                session_id,
            )

    return OutputSnapshot(
        session_id=session_id,
        file=rendered,
        source=current_source,
        layers=current_layers,
        model_logs=model_logs,
        audit_boundary_hash=tx.committed_events[0]["event_hash"],
    )
