"""Execute AIADR source analysis workflows."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import assert_never

from app.core.ids import new_finding_id
from app.core.paths import outputs_dir
from app.domain.finding import DocxPictureSurface, Finding, PdfPageSurface
from app.domain.layer import Layer
from app.errors import ApplicationError, ErrorCode, app_error
from app.findings.anchoring import (
    anchor_audio_findings,
    anchor_docx_findings,
    anchor_image_findings,
    anchor_text_findings,
    deduplicate_audio_findings,
)
from app.findings.extraction import (
    ExtractionKind,
    ExtractionResult,
    FindingExtractionError,
    extract_findings,
)
from app.inference.detection import DetectionOutput, DetectionSession, ModelCallContext
from app.inference.payloads import (
    audio_source_payload,
    docx_source_payload,
    image_source_payload,
    text_source_payload,
)
from app.instruction_sets import (
    InstructionSet,
    PromptKey,
    get_active_instruction_set,
)
from app.models.store import get_active_model
from app.operations.analyze.audit import (
    AnalysisContext,
    analysis_cancelled,
    analysis_completed,
    analysis_failed,
    analysis_setup_failed,
    analysis_started,
)
from app.operations.analyze.notifications import publish_progress
from app.operations.analyze.values import (
    AnalysisResult,
    PdfAnalysisResult,
    SourceInput,
)
from app.policies.mapper import map_finding_to_layer
from app.preprocessing.audio import build_audio_inputs
from app.preprocessing.image import build_image_input
from app.preprocessing.pdf import build_pdf_page_inputs
from app.preprocessing.text import build_text_inputs
from app.sessions.records import SessionRecord, SessionStatus
from app.sources.docx_images import DocxImageOccurrence
from app.sources.docx_text import DocxTextBlock
from app.sources.kinds import SourceKind
from app.sources.records import (
    AudioSourceRecord,
    DocumentSourceRecord,
    DocumentState,
    DocxDocumentState,
    ImageSourceRecord,
    PdfDocumentState,
    TextDocumentState,
)
from app.storage import model_log_store, review_store, session_store, source_store
from app.storage.file_store import output_path, require_docx_image_asset, require_source_path
from app.storage.transaction import transaction

logger = logging.getLogger(__name__)

MODEL_CALL_MESSAGE = "Calling configured model endpoint"


def _start_analysis(context: AnalysisContext) -> None:
    with transaction() as tx:
        session_store.update_session_with_connection(
            tx.connection,
            context.session_id,
            error_message=None,
        )
        tx.record(analysis_started(context))


def _complete_analysis(
    context: AnalysisContext,
    session: SessionRecord,
    instruction_set: InstructionSet,
    result: AnalysisResult,
    layers: list[Layer],
) -> None:
    completed_event = analysis_completed(
        context,
        finding_count=len(result.findings),
        layer_count=len(layers),
        rejected_count=result.rejected_count,
        page_count=(result.page_count if isinstance(result, PdfAnalysisResult) else None),
    )

    with transaction() as tx:
        session_store.replace_instruction_set_with_connection(
            tx.connection,
            context.session_id,
            instruction_set_id=instruction_set.id,
            instruction_set_content_hash=instruction_set.content_hash,
            snapshot_bytes=instruction_set.snapshot_bytes,
        )
        if isinstance(result, PdfAnalysisResult):
            if not isinstance(session.source, DocumentSourceRecord) or not isinstance(
                session.source.state,
                PdfDocumentState,
            ):
                raise TypeError("document result requires a fixed-layout document source")
            updated_source = session.source.model_copy(
                update={
                    "state": PdfDocumentState(
                        page_count=result.page_count,
                    )
                }
            )
            session_store.replace_source_metadata_with_connection(
                tx.connection,
                context.session_id,
                updated_source,
            )
            source_store.replace_pdf_lines_with_connection(
                tx.connection,
                context.session_id,
                (),
            )
        review_store.replace_layers_with_connection(
            tx.connection,
            context.session_id,
            layers,
        )
        session_store.update_session_with_connection(
            tx.connection,
            context.session_id,
            status=SessionStatus.REVIEW_READY,
            error_message=None,
        )
        tx.record(completed_event)


def status_after_failure(starting_status: SessionStatus) -> SessionStatus:
    """Preserve an existing usable review after a failed replacement."""
    return (
        SessionStatus.REVIEW_READY
        if starting_status is SessionStatus.REVIEW_READY
        else SessionStatus.ERROR
    )


def status_after_cancellation(starting_status: SessionStatus) -> SessionStatus:
    """Preserve an existing usable review after cancelled replacement."""
    return (
        SessionStatus.REVIEW_READY
        if starting_status is SessionStatus.REVIEW_READY
        else SessionStatus.CANCELLED
    )


def _fail_setup(
    session: SessionRecord,
    error: ApplicationError,
) -> None:
    with transaction() as tx:
        session_store.update_session_with_connection(
            tx.connection,
            session.session_id,
            status=status_after_failure(session.status),
            error_message=error.message,
        )
        tx.record(
            analysis_setup_failed(
                session=session,
                error=error,
            )
        )


def _fail_analysis(
    context: AnalysisContext,
    starting_session: SessionRecord,
    error: ApplicationError,
) -> None:
    with transaction() as tx:
        session_store.update_session_with_connection(
            tx.connection,
            context.session_id,
            status=status_after_failure(starting_session.status),
            error_message=error.message,
        )
        tx.record(analysis_failed(context, error))


def _cancel_analysis(
    context: AnalysisContext,
    starting_session: SessionRecord,
) -> None:
    with transaction() as tx:
        session_store.update_session_with_connection(
            tx.connection,
            context.session_id,
            status=status_after_cancellation(starting_session.status),
            error_message=None,
        )
        tx.record(analysis_cancelled(context))


def _extract_detection_findings(
    output: DetectionOutput,
    *,
    kind: ExtractionKind,
    model: str,
    page: int | None = None,
) -> ExtractionResult:
    """Extract domain findings and diagnostics from one provider response."""
    try:
        result = extract_findings(output.content, kind=kind, page=page, created_by=model)
    except FindingExtractionError as exc:
        model_log_store.record_parse_failure(output.log_id)
        raise app_error(
            ErrorCode.PROVIDER_RESPONSE_INVALID,
            details={"model": model, "kind": kind, "page": page},
        ) from exc
    model_log_store.record_parse_success(
        output.log_id,
        parsed_finding_count=len(result.findings),
        rejected_finding_count=result.rejected_count,
    )
    return result


async def analyze_text(
    source: SourceInput,
) -> AnalysisResult:
    """Analyze every line of a text source through bounded model requests."""
    findings: list[Finding] = []
    rejected_count = 0
    async with DetectionSession(source.model) as detection:
        text_inputs = await asyncio.to_thread(
            build_text_inputs,
            source.source_path,
            request_byte_limit=await detection.source_payload_byte_budget(source.system_prompt),
        )
        if not any(item.lines for item in text_inputs):
            return AnalysisResult(findings=(), rejected_count=0)
        for index, text_input in enumerate(text_inputs, start=1):
            await publish_progress(
                source.session_id,
                progress=0.15 + (0.45 * index / len(text_inputs)),
                message=MODEL_CALL_MESSAGE,
            )
            detection_output = await detection.detect_text(
                context=ModelCallContext(
                    session_id=source.session_id,
                    kind=SourceKind.DOCUMENT,
                ),
                system_prompt=source.system_prompt,
                source_payload=text_source_payload(text_input.lines),
            )
            extracted = _extract_detection_findings(
                detection_output,
                kind=ExtractionKind.TEXT,
                model=detection.model,
            )
            anchored = anchor_text_findings(list(extracted.findings), text_input.lines)
            batch_rejected_count = (
                extracted.rejected_count + len(extracted.findings) - len(anchored)
            )
            rejected_count += batch_rejected_count
            if batch_rejected_count:
                logger.warning(
                    "Rejected %d invalid text findings session_id=%s",
                    batch_rejected_count,
                    source.session_id,
                )
            findings.extend(anchored)
    return AnalysisResult(
        findings=tuple(findings),
        rejected_count=rejected_count,
    )


async def analyze_pdf(
    source: SourceInput,
) -> PdfAnalysisResult:
    """Analyze every PDF page as a visual surface."""
    with TemporaryDirectory(prefix=".pdf-analysis-", dir=outputs_dir(source.session_id)) as raw:
        page_inputs = await asyncio.to_thread(
            build_pdf_page_inputs,
            source.source_path,
            Path(raw),
        )
        findings: list[Finding] = []
        rejected_count = 0

        async with DetectionSession(source.model) as detection:
            for page_input in page_inputs:
                await publish_progress(
                    source.session_id,
                    progress=0.15 + (0.45 * page_input.page / len(page_inputs)),
                    page=page_input.page,
                    message=MODEL_CALL_MESSAGE,
                )
                image_bytes = await asyncio.to_thread(page_input.image_path.read_bytes)
                detection_output = await detection.detect_vision(
                    context=ModelCallContext(
                        session_id=source.session_id,
                        kind=SourceKind.DOCUMENT,
                        page=page_input.page,
                    ),
                    system_prompt=source.system_prompt,
                    source_payload=image_source_payload(),
                    image_bytes=image_bytes,
                    mime_type=page_input.mime_type,
                )
                extracted = _extract_detection_findings(
                    detection_output,
                    kind=ExtractionKind.IMAGE,
                    model=detection.model,
                    page=page_input.page,
                )
                anchored = anchor_image_findings(
                    list(extracted.findings),
                    PdfPageSurface(page=page_input.page),
                )
                page_rejected_count = (
                    extracted.rejected_count + len(extracted.findings) - len(anchored)
                )
                rejected_count += page_rejected_count
                if page_rejected_count:
                    logger.warning(
                        "Rejected %d invalid PDF image findings session_id=%s page=%d",
                        page_rejected_count,
                        source.session_id,
                        page_input.page,
                    )
                findings.extend(anchored)
        return PdfAnalysisResult(
            findings=tuple(findings),
            rejected_count=rejected_count,
            page_count=page_inputs[0].page_count,
        )


def _docx_batches(
    blocks: list[DocxTextBlock],
    byte_limit: int | None,
) -> list[tuple[DocxTextBlock, ...]]:
    content_blocks = [block for block in blocks if block.text.strip()]
    if not content_blocks:
        return []
    if byte_limit is None:
        return [tuple(content_blocks)]
    batches: list[tuple[DocxTextBlock, ...]] = []
    current: list[DocxTextBlock] = []
    size = 0
    for block in content_blocks:
        block_size = len(block.text.encode()) + len(block.block_id.encode()) + 32
        if block_size > byte_limit:
            raise app_error(
                ErrorCode.TEXT_LINE_TOO_LARGE,
                details={"line_id": block.block_id, "line_bytes": block_size},
            )
        if current and size + block_size > byte_limit:
            batches.append(tuple(current))
            current = []
            size = 0
        current.append(block)
        size += block_size
    if current:
        batches.append(tuple(current))
    return batches


async def analyze_docx(source: SourceInput) -> AnalysisResult:
    """Analyze canonical DOCX text, then each distinct normalized picture."""
    blocks = source_store.get_docx_blocks(source.session_id)
    occurrences = source_store.get_docx_image_occurrences(source.session_id)
    image_groups = _docx_image_groups(occurrences)
    if image_groups and source.image_prompt is None:
        raise app_error(
            ErrorCode.UNSUPPORTED_PROMPT_KIND,
            details={"source_kind": SourceKind.IMAGE},
        )
    findings: list[Finding] = []
    rejected_count = 0
    preview_lines = source_store.get_pdf_lines(source.session_id)
    async with DetectionSession(source.model) as detection:
        batches = _docx_batches(
            blocks,
            await detection.source_payload_byte_budget(source.system_prompt),
        )
        call_count = len(batches) + len(image_groups)
        completed_calls = 0
        for batch in batches:
            await publish_progress(
                source.session_id,
                progress=0.15 + (0.55 * (completed_calls + 1) / max(call_count, 1)),
                message=MODEL_CALL_MESSAGE,
            )
            detection_output = await detection.detect_text(
                context=ModelCallContext(
                    session_id=source.session_id,
                    kind=SourceKind.DOCUMENT,
                ),
                system_prompt=source.system_prompt,
                source_payload=docx_source_payload(batch),
            )
            extracted = _extract_detection_findings(
                detection_output,
                kind=ExtractionKind.TEXT,
                model=detection.model,
            )
            anchored = anchor_docx_findings(
                list(extracted.findings),
                batch,
                source_sha256=source.source_sha256,
                preview_lines=preview_lines,
            )
            rejected_count += extracted.rejected_count + len(extracted.findings) - len(anchored)
            findings.extend(anchored)
            completed_calls += 1

        for group in image_groups:
            representative = group[0]
            assert representative.asset_filename is not None
            assert representative.normalized_sha256 is not None
            await publish_progress(
                source.session_id,
                progress=0.15 + (0.55 * (completed_calls + 1) / max(call_count, 1)),
                message=MODEL_CALL_MESSAGE,
            )
            image_path = require_docx_image_asset(
                source.session_id,
                representative.asset_filename,
                representative.normalized_sha256,
            )
            detection_output = await detection.detect_vision(
                context=ModelCallContext(
                    session_id=source.session_id,
                    kind=SourceKind.DOCUMENT,
                ),
                system_prompt=source.image_prompt or "",
                source_payload=image_source_payload(),
                image_bytes=await asyncio.to_thread(image_path.read_bytes),
                mime_type="image/png",
            )
            extracted = _extract_detection_findings(
                detection_output,
                kind=ExtractionKind.IMAGE,
                model=detection.model,
            )
            accepted = 0
            for occurrence in group:
                anchored = anchor_image_findings(
                    list(extracted.findings),
                    DocxPictureSurface(occurrence_id=occurrence.occurrence_id),
                )
                findings.extend(
                    finding.model_copy(update={"id": new_finding_id()}) for finding in anchored
                )
                accepted += len(anchored)
            rejected_count += extracted.rejected_count + (
                len(extracted.findings) * len(group) - accepted
            )
            completed_calls += 1
    return AnalysisResult(findings=tuple(findings), rejected_count=rejected_count)


def _docx_image_groups(
    occurrences: list[DocxImageOccurrence],
) -> list[tuple[DocxImageOccurrence, ...]]:
    """Group targetable occurrences by exact normalized bytes in source order."""
    groups: dict[str, list[DocxImageOccurrence]] = {}
    for occurrence in occurrences:
        if not occurrence.targetable or occurrence.normalized_sha256 is None:
            continue
        groups.setdefault(occurrence.normalized_sha256, []).append(occurrence)
    return [tuple(group) for group in groups.values()]


async def analyze_document_source(
    source: SourceInput,
    state: DocumentState,
) -> AnalysisResult:
    """Route a document to the implementation selected by its layout state."""
    match state:
        case TextDocumentState():
            return await analyze_text(source)
        case PdfDocumentState():
            return await analyze_pdf(source)
        case DocxDocumentState():
            return await analyze_docx(source)
        case unexpected_state:
            assert_never(unexpected_state)


async def analyze_image(
    source: SourceInput,
) -> AnalysisResult:
    """Analyze an orientation-corrected image source."""
    image_input = await asyncio.to_thread(
        build_image_input,
        source.source_path,
        output_path(source.session_id, "analysis-image.jpg"),
    )
    await publish_progress(
        source.session_id,
        progress=0.25,
        message=MODEL_CALL_MESSAGE,
    )
    image_bytes = await asyncio.to_thread(image_input.path.read_bytes)
    async with DetectionSession(source.model) as detection:
        detection_output = await detection.detect_vision(
            context=ModelCallContext(
                session_id=source.session_id,
                kind=SourceKind.IMAGE,
            ),
            system_prompt=source.system_prompt,
            source_payload=image_source_payload(),
            image_bytes=image_bytes,
            mime_type=image_input.mime_type,
        )
    extracted = _extract_detection_findings(
        detection_output,
        kind=ExtractionKind.IMAGE,
        model=detection.model,
    )
    if extracted.rejected_count:
        logger.warning(
            "Rejected %d invalid image findings session_id=%s",
            extracted.rejected_count,
            source.session_id,
        )
    return AnalysisResult(
        findings=extracted.findings,
        rejected_count=extracted.rejected_count,
    )


async def analyze_audio(
    source: SourceInput,
) -> AnalysisResult:
    """Analyze canonical WAV attachments through the selected provider format."""
    audio_inputs = await asyncio.to_thread(
        build_audio_inputs,
        source.source_path,
        output_path(source.session_id, "audio-inputs"),
    )
    findings: list[Finding] = []
    rejected_count = 0
    async with DetectionSession(source.model) as detection:
        for index, audio_input in enumerate(audio_inputs, start=1):
            await publish_progress(
                source.session_id,
                progress=0.15 + (0.45 * index / len(audio_inputs)),
                message=MODEL_CALL_MESSAGE,
            )
            audio_bytes = await asyncio.to_thread(audio_input.path.read_bytes)
            detection_output = await detection.detect_audio(
                context=ModelCallContext(
                    session_id=source.session_id,
                    kind=SourceKind.AUDIO,
                ),
                system_prompt=source.system_prompt,
                source_payload=audio_source_payload(
                    start_time=audio_input.start_time,
                    duration_seconds=audio_input.duration_seconds,
                ),
                audio_bytes=audio_bytes,
            )
            extracted = _extract_detection_findings(
                detection_output,
                kind=ExtractionKind.AUDIO,
                model=detection.model,
            )
            anchored = anchor_audio_findings(
                list(extracted.findings),
                attachment_start_seconds=audio_input.start_time,
                attachment_duration_seconds=audio_input.duration_seconds,
                source_duration_seconds=audio_input.source_duration_seconds,
            )
            rejected_count += extracted.rejected_count + len(extracted.findings) - len(anchored)
            findings.extend(anchored)
    deduplicated = deduplicate_audio_findings(findings)
    rejected_count += len(findings) - len(deduplicated)
    if rejected_count:
        logger.warning(
            "Rejected %d invalid or duplicate audio findings session_id=%s",
            rejected_count,
            source.session_id,
        )
    return AnalysisResult(
        findings=tuple(deduplicated),
        rejected_count=rejected_count,
    )


def _resolve_source_input(
    session: SessionRecord,
) -> tuple[SourceInput, InstructionSet, AnalysisContext]:
    model = get_active_model()
    instruction_set = get_active_instruction_set()
    image_prompt: str | None = None
    try:
        if isinstance(session.source, DocumentSourceRecord):
            match session.source.state:
                case TextDocumentState():
                    prompt_key = PromptKey.TEXT
                case DocxDocumentState() as state:
                    prompt_key = PromptKey.TEXT
                    if state.targetable_image_count:
                        image_prompt = instruction_set.prompt_for(PromptKey.IMAGE)
                case PdfDocumentState():
                    prompt_key = PromptKey.IMAGE
                case unexpected_state:
                    assert_never(unexpected_state)
        elif isinstance(session.source, ImageSourceRecord):
            prompt_key = PromptKey.IMAGE
        elif isinstance(session.source, AudioSourceRecord):
            prompt_key = PromptKey.AUDIO
        else:
            assert_never(session.source)
        system_prompt = instruction_set.prompt_for(prompt_key)
    except KeyError as exc:
        raise app_error(
            ErrorCode.UNSUPPORTED_PROMPT_KIND,
            details={"source_kind": session.source.kind},
        ) from exc
    source_path = require_source_path(session.session_id, session.source.file)
    context = AnalysisContext(
        session_id=session.session_id,
        source_kind=session.source.kind,
        model_id=model.model_id,
        model=model.provider.model,
        instruction_set_id=instruction_set.id,
        instruction_set_content_hash=instruction_set.content_hash,
    )
    return (
        SourceInput(
            session_id=session.session_id,
            source_path=source_path,
            source_sha256=session.source.file.sha256,
            model=model,
            system_prompt=system_prompt,
            image_prompt=image_prompt,
        ),
        instruction_set,
        context,
    )


async def analyze(session_id: str) -> int:
    """Analyze one persisted session with the active model and policy."""
    starting_session = session_store.require_session(session_id)
    try:
        source, instruction_set, context = _resolve_source_input(starting_session)
    except ApplicationError as error:
        _fail_setup(starting_session, error)
        raise
    except Exception as error:
        translated = app_error(ErrorCode.INTERNAL_ERROR)
        logger.error(
            "Unexpected analysis setup failure session_id=%s correlation_id=%s",
            session_id,
            translated.correlation_id,
        )
        _fail_setup(starting_session, translated)
        raise translated from error

    durable_start_committed = False

    try:
        _start_analysis(context)
        durable_start_committed = True
        await publish_progress(
            session_id,
            progress=0.05,
            message="Building model input",
        )

        match starting_session.source:
            case DocumentSourceRecord() as document:
                result = await analyze_document_source(source, document.state)
            case ImageSourceRecord():
                result = await analyze_image(source)
            case AudioSourceRecord():
                result = await analyze_audio(source)
            case unexpected_source:
                assert_never(unexpected_source)

        await publish_progress(
            session_id,
            progress=0.65,
            message="Mapping policy",
        )
        layers = [map_finding_to_layer(item, instruction_set.policy) for item in result.findings]
        _complete_analysis(context, starting_session, instruction_set, result, layers)
        durable_start_committed = False
    except asyncio.CancelledError:
        if durable_start_committed:
            _cancel_analysis(context, starting_session)
        raise
    except ApplicationError as error:
        if durable_start_committed:
            _fail_analysis(context, starting_session, error)
        raise
    except Exception as exc:
        translated = app_error(ErrorCode.INTERNAL_ERROR)
        logger.error(
            "Unexpected analysis failure session_id=%s correlation_id=%s",
            session_id,
            translated.correlation_id,
        )
        if durable_start_committed:
            _fail_analysis(context, starting_session, translated)
        raise translated from exc
    return len(result.findings)
