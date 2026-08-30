"""Application operations for reviewer sessions, findings, and layers."""

from __future__ import annotations

from typing import assert_never, cast

from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from app.audit.events import ActorType, AuditEvent, AuditEventType
from app.core.ids import new_finding_id
from app.core.task_registry import is_active
from app.domain.finding import (
    AudioTarget,
    DocumentTarget,
    DocxPictureSurface,
    DocxTextLocator,
    FileImageSurface,
    Finding,
    FindingOrigin,
    FindingTarget,
    ImageTarget,
    PdfPageSurface,
    PlainTextLocator,
)
from app.domain.layer import EffectSource, Layer, LayerAction, LayerEffect, is_effect_supported
from app.errors import ErrorCode, app_error
from app.instruction_sets import require_session_instruction_set
from app.instruction_sets.instruction_set import InstructionPolicy
from app.policies.mapper import map_finding_to_layer, reclassify_layer
from app.preprocessing.text import build_text_inputs
from app.sessions.records import SessionRecord
from app.sources.docx_targets import is_valid_locator
from app.sources.records import (
    AudioSourceRecord,
    DocumentSourceRecord,
    DocxDocumentState,
    ImageSourceRecord,
    PdfDocumentState,
    TextDocumentState,
)
from app.storage import review_store, session_store, source_store
from app.storage.file_store import require_source_path
from app.storage.transaction import transaction

_TARGET_ADAPTER: TypeAdapter[FindingTarget] = TypeAdapter(FindingTarget)


def _require_review_writable(session_id: str) -> None:
    if is_active(session_id):
        raise app_error(
            ErrorCode.ANALYSIS_ALREADY_RUNNING,
            details={"session_id": session_id},
        )


def parse_target(value: object) -> FindingTarget:
    """Convert an API target model into the domain target union."""
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return _TARGET_ADAPTER.validate_python(data)


def require_session_instruction_policy(session_id: str) -> InstructionPolicy:
    """Restore the immutable policy locked to a session."""
    return require_session_instruction_set(session_id).policy


def _validate_entity_type(entity_type: str, policy: InstructionPolicy) -> None:
    if entity_type == "unknown" or policy.rule_for(entity_type) is not None:
        return
    raise app_error(
        ErrorCode.INVALID_FINDING_UPDATE,
        details={"reviewed_entity_type": entity_type},
    )


def _audit_entity_type(entity_type: str | None, policy: InstructionPolicy) -> str:
    if entity_type == "unknown" or (
        entity_type is not None and policy.rule_for(entity_type) is not None
    ):
        return entity_type
    return "unknown"


def classification_options(session_id: str) -> list[dict[str, str | None]]:
    """Return reviewer-safe classification choices from the locked policy."""
    policy = require_session_instruction_policy(session_id)
    options = [
        {
            "entity_type": rule.entity_type,
            "display_name": rule.display_name,
            "description": rule.description,
        }
        for rule in policy.entity_rules
    ]
    options.append(
        {
            "entity_type": "unknown",
            "display_name": "Unknown",
            "description": "Use policy defaults without a more specific classification.",
        }
    )
    return sorted(
        options,
        key=lambda item: (
            str(item["display_name"]).casefold(),
            str(item["entity_type"]),
        ),
    )


def _validate_target(session: SessionRecord, target: FindingTarget) -> None:
    source = session.source
    if isinstance(target, ImageTarget):
        surface = target.surface
        if isinstance(source, ImageSourceRecord) and isinstance(surface, FileImageSurface):
            return
        if (
            isinstance(source, DocumentSourceRecord)
            and isinstance(source.state, PdfDocumentState)
            and isinstance(surface, PdfPageSurface)
        ):
            if surface.page <= source.state.page_count:
                return
            raise app_error(
                ErrorCode.PDF_PAGE_OUT_OF_RANGE,
                details={"page": surface.page, "page_count": source.state.page_count},
            )
        if (
            isinstance(source, DocumentSourceRecord)
            and isinstance(source.state, DocxDocumentState)
            and isinstance(surface, DocxPictureSurface)
        ):
            occurrence = next(
                (
                    item
                    for item in source_store.get_docx_image_occurrences(session.session_id)
                    if item.occurrence_id == surface.occurrence_id
                ),
                None,
            )
            if occurrence is not None and occurrence.targetable:
                return
            raise app_error(
                ErrorCode.INVALID_FINDING_UPDATE,
                details={"reason": "docx_picture_target_invalid"},
            )
        raise app_error(
            ErrorCode.INVALID_FINDING_UPDATE,
            details={"reason": "image_surface_mismatch"},
        )
    if target.kind != source.kind:
        raise app_error(
            ErrorCode.INVALID_FINDING_UPDATE,
            details={"source_kind": session.source.kind, "target_kind": target.kind},
        )
    if isinstance(target, DocumentTarget) and isinstance(source, DocumentSourceRecord):
        locator = target.locator
        if isinstance(source.state, TextDocumentState):
            if not isinstance(locator, PlainTextLocator):
                raise app_error(
                    ErrorCode.INVALID_FINDING_UPDATE,
                    details={"reason": "source_format_mismatch"},
                )
            source_path = require_source_path(session.session_id, source.file)
            lines = {
                line.line_id: line.text
                for text_input in build_text_inputs(source_path, request_byte_limit=None)
                for line in text_input.lines
            }
            if locator.exact_text in lines.get(locator.line_id, ""):
                return
            raise app_error(
                ErrorCode.INVALID_FINDING_UPDATE,
                details={"line_id": locator.line_id, "reason": "exact_text_not_found"},
            )
        if isinstance(source.state, PdfDocumentState):
            raise app_error(
                ErrorCode.INVALID_FINDING_UPDATE,
                details={"reason": "pdf_requires_visual_target"},
            )
        if isinstance(source.state, DocxDocumentState):
            if not isinstance(locator, DocxTextLocator):
                raise app_error(
                    ErrorCode.INVALID_FINDING_UPDATE,
                    details={"reason": "source_format_mismatch"},
                )
            blocks = {
                block.block_id: block
                for block in source_store.get_docx_blocks(session.session_id)
            }
            block = blocks.get(locator.block_id)
            if (
                block is not None
                and is_valid_locator(
                    block,
                    locator,
                    source_store.get_pdf_lines(session.session_id),
                    source_sha256=source.file.sha256,
                )
            ):
                return
            raise app_error(ErrorCode.INVALID_DOCX_TEXT_TARGET)
        assert_never(source.state)
    if isinstance(target, AudioTarget):
        audio_source = session.source
        if not isinstance(audio_source, AudioSourceRecord):
            raise app_error(
                ErrorCode.INVALID_FINDING_UPDATE,
                details={"reason": "source_kind_mismatch"},
            )
        if target.range.end_time <= audio_source.duration_seconds:
            return
        raise app_error(
            ErrorCode.INVALID_FINDING_UPDATE,
            details={
                "duration_seconds": audio_source.duration_seconds,
                "end_time": target.range.end_time,
            },
        )


def add_manual_finding(
    session_id: str,
    *,
    label: str,
    reviewed_entity_type: str,
    description: str,
    reason: str,
    target: FindingTarget,
) -> Layer:
    """Create a reviewer-authored finding and its default layer."""
    _require_review_writable(session_id)
    session = session_store.require_session(session_id)
    policy = require_session_instruction_policy(session_id)
    _validate_entity_type(reviewed_entity_type, policy)
    _validate_target(session, target)
    finding = Finding(
        id=new_finding_id(),
        target=target,
        detected_entity_type=None,
        reviewed_entity_type=reviewed_entity_type,
        label=label,
        description=description,
        reason=reason,
        origin=FindingOrigin.REVIEWER,
        created_by="Reviewer-001",
    )
    layer = map_finding_to_layer(finding, policy)
    with transaction() as tx:
        review_store.add_layer_with_connection(tx.connection, session_id, layer)
        tx.record(
            AuditEvent(
                session_id=session_id,
                event_type=AuditEventType.REVIEW_FINDING_ADDED,
                payload={
                    "finding_id": finding.id,
                    "reviewed_entity_type": _audit_entity_type(reviewed_entity_type, policy),
                    "effective_entity_type": _audit_entity_type(
                        layer.finding.effective_entity_type,
                        policy,
                    ),
                },
                actor_id="Reviewer-001",
                actor_type=ActorType.REVIEWER,
            ),
        )
    return layer


def update_review_finding(session_id: str, finding_id: str, patch: dict[str, object]) -> Layer:
    """Apply reviewer-editable finding changes and append an audit event."""
    _require_review_writable(session_id)
    policy = require_session_instruction_policy(session_id)
    if "reviewed_entity_type" in patch and patch["reviewed_entity_type"] is not None:
        _validate_entity_type(str(patch["reviewed_entity_type"]), policy)
    session = session_store.require_session(session_id)
    current = review_store.get_layer_for_finding(session_id, finding_id)
    if current is None:
        raise app_error(
            ErrorCode.FINDING_NOT_FOUND,
            details={"session_id": session_id, "finding_id": finding_id},
        )
    try:
        finding = Finding.model_validate(
            {
                **current.finding.model_dump(exclude_computed_fields=True),
                **patch,
                "edited": True,
            }
        )
    except ValidationError as exc:
        raise app_error(
            ErrorCode.INVALID_FINDING_UPDATE,
            details={"reason": str(exc)},
        ) from exc
    if finding.reviewed_entity_type is None and finding.detected_entity_type is None:
        raise app_error(
            ErrorCode.INVALID_FINDING_UPDATE,
            details={"reviewed_entity_type": None},
        )
    if "target" in patch:
        _validate_target(session, finding.target)
    previous_finding = current.finding
    candidate = (
        reclassify_layer(current, finding, policy)
        if "reviewed_entity_type" in patch
        else current.model_copy(update={"finding": finding})
    )
    updated_fields: list[JsonValue] = [field for field in sorted(patch)]
    event = AuditEvent(
        session_id=session_id,
        event_type=AuditEventType.REVIEW_FINDING_UPDATED,
        payload={
            "finding_id": finding_id,
            "updated_fields": updated_fields,
            "detected_entity_type": _audit_entity_type(finding.detected_entity_type, policy),
            "previous_reviewed_entity_type": _audit_entity_type(
                previous_finding.reviewed_entity_type,
                policy,
            ),
            "reviewed_entity_type": _audit_entity_type(
                finding.reviewed_entity_type,
                policy,
            ),
            "previous_effective_entity_type": _audit_entity_type(
                previous_finding.effective_entity_type,
                policy,
            ),
            "effective_entity_type": _audit_entity_type(
                finding.effective_entity_type,
                policy,
            ),
        },
        actor_id="Reviewer-001",
        actor_type=ActorType.REVIEWER,
    )
    with transaction() as tx:
        updated = review_store.save_layer_with_connection(
            tx.connection,
            session_id,
            candidate,
        )
        tx.record(event)
    return updated


def update_review_layer(
    session_id: str,
    layer_id: str,
    updates: dict[str, object],
) -> Layer:
    """Apply reviewer-editable layer changes and append an audit event."""
    _require_review_writable(session_id)
    with transaction() as tx:
        layers = review_store.get_layers_with_connection(
            tx.connection,
            session_id,
            [layer_id],
        )
        if not layers:
            raise app_error(
                ErrorCode.LAYER_NOT_FOUND,
                details={"session_id": session_id, "layer_id": layer_id},
            )
        current = layers[0]
        patch = dict(updates)
        if {"action", "effect"}.intersection(patch):
            patch["effect_source"] = EffectSource.REVIEWER
        action = cast(LayerAction, patch.get("action", current.action))
        effect = cast(LayerEffect, patch.get("effect", current.effect))
        if not is_effect_supported(current.finding.kind, action, effect):
            raise app_error(
                ErrorCode.INVALID_ACTION_EFFECT,
                details={"kind": current.finding.kind, "action": action, "effect": effect},
            )
        accepts_custom_text = (
            action is LayerAction.PSEUDONYMIZE
            and effect is LayerEffect.TOKEN_REPLACE
        )
        custom_text = patch.get("custom_text")
        if (
            not accepts_custom_text
            and (current.custom_text is not None or "custom_text" in patch)
        ) or (
            accepts_custom_text
            and isinstance(custom_text, str)
            and not custom_text.strip()
        ):
            patch["custom_text"] = None
        try:
            candidate = Layer.model_validate(
                {**current.model_dump(exclude_computed_fields=True), **patch}
            )
        except ValidationError as exc:
            raise app_error(ErrorCode.INVALID_LAYER_UPDATE, details={"reason": str(exc)}) from exc
        updated = review_store.save_layer_with_connection(
            tx.connection,
            session_id,
            candidate,
        )
        updated_fields: list[JsonValue] = [field for field in sorted(patch)]
        tx.record(
            AuditEvent(
                session_id=session_id,
                event_type=AuditEventType.REVIEW_LAYER_UPDATED,
                payload={
                    "layer_id": layer_id,
                    "updated_fields": updated_fields,
                    "previous_action": current.action,
                    "action": updated.action,
                    "previous_effect": current.effect,
                    "effect": updated.effect,
                    "previous_effect_source": current.effect_source,
                    "effect_source": updated.effect_source,
                },
                actor_id="Reviewer-001",
                actor_type=ActorType.REVIEWER,
            ),
        )
    return updated


def reset_effect_override(session_id: str, layer_id: str) -> Layer:
    """Restore one layer's action and effect from its locked session policy."""
    _require_review_writable(session_id)
    policy = require_session_instruction_policy(session_id)
    with transaction() as tx:
        layers = review_store.get_layers_with_connection(
            tx.connection,
            session_id,
            [layer_id],
        )
        if not layers:
            raise app_error(
                ErrorCode.LAYER_NOT_FOUND,
                details={"session_id": session_id, "layer_id": layer_id},
            )
        current = layers[0]
        updated = reclassify_layer(
            current.model_copy(update={"effect_source": EffectSource.POLICY}),
            current.finding,
            policy,
        )
        updated = review_store.save_layer_with_connection(
            tx.connection,
            session_id,
            updated,
        )
        tx.record(
            AuditEvent(
                session_id=session_id,
                event_type=AuditEventType.REVIEW_EFFECT_RESET,
                payload={
                    "layer_id": layer_id,
                    "previous_action": current.action,
                    "action": updated.action,
                    "previous_effect": current.effect,
                    "effect": updated.effect,
                    "previous_effect_source": current.effect_source,
                    "effect_source": updated.effect_source,
                },
                actor_id="Reviewer-001",
                actor_type=ActorType.REVIEWER,
            ),
        )
    return updated
