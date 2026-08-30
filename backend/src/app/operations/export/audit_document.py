"""Content-minimized audit projection for review export bundles."""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

from app.audit.event_log import PersistedAuditEvent
from app.core.version import application_version, source_identity
from app.domain.finding import (
    AudioTarget,
    DocumentTarget,
    DocxTextLocator,
    Finding,
    ImageTarget,
    PlainTextLocator,
)
from app.domain.layer import Layer, LayerEffect
from app.files.descriptors import fingerprint_file
from app.inference.model_log import ModelInteractionLog
from app.instruction_sets.instruction_set import InstructionPolicy
from app.operations.output import OutputSnapshot
from app.preprocessing.text import build_text_inputs
from app.sources.records import DocumentSourceRecord, TextDocumentState


def _safe_entity_type(value: str | None, policy: InstructionPolicy) -> str:
    if value == "unknown" or (value is not None and policy.rule_for(value) is not None):
        return value
    return "unknown"


def _plain_text_lines(output: OutputSnapshot, source_path: Path) -> dict[str, str]:
    if not isinstance(output.source, DocumentSourceRecord) or not isinstance(
        output.source.state,
        TextDocumentState,
    ):
        return {}
    inputs = build_text_inputs(source_path, request_byte_limit=None)
    return {line.line_id: line.text for item in inputs for line in item.lines}


def _plain_text_target(
    locator: PlainTextLocator,
    source_lines: dict[str, str],
) -> dict[str, object]:
    projection: dict[str, object] = {
        "kind": "document",
        "format": locator.format,
        "line_id": locator.line_id,
    }
    line = source_lines.get(locator.line_id)
    if line is None:
        return projection
    start = line.find(locator.exact_text)
    if start < 0 or line.find(locator.exact_text, start + 1) >= 0:
        return projection
    projection.update(start=start, end=start + len(locator.exact_text))
    return projection


def _target_projection(
    finding: Finding,
    source_lines: dict[str, str],
) -> dict[str, object]:
    target = finding.target
    if isinstance(target, ImageTarget):
        return {
            "kind": target.kind,
            "surface": target.surface.model_dump(mode="json"),
            "region": target.region.model_dump(mode="json"),
        }
    if isinstance(target, AudioTarget):
        return {
            "kind": target.kind,
            "start_time": target.range.start_time,
            "end_time": target.range.end_time,
        }
    if isinstance(target, DocumentTarget):
        locator = target.locator
        if isinstance(locator, PlainTextLocator):
            return _plain_text_target(locator, source_lines)
        if isinstance(locator, DocxTextLocator):
            return {
                "kind": target.kind,
                "format": locator.format,
                "page": locator.page,
                "line_id": locator.line_id,
                "story_kind": locator.story_kind,
                "part_uri": locator.part_uri,
                "block_id": locator.block_id,
                "start": locator.start,
                "end": locator.end,
            }
        assert_never(locator)
    assert_never(target)


def _layer_projection(
    layer: Layer,
    policy: InstructionPolicy,
    source_lines: dict[str, str],
) -> dict[str, object]:
    finding = layer.finding
    projection: dict[str, object] = {
        "finding_id": finding.id,
        "layer_id": layer.id,
        "detected_entity_type": _safe_entity_type(finding.detected_entity_type, policy),
        "reviewed_entity_type": _safe_entity_type(finding.reviewed_entity_type, policy),
        "effective_entity_type": _safe_entity_type(finding.effective_entity_type, policy),
        "privacy_category": finding.privacy_category,
        "special_category_type": finding.special_category_type,
        "data_subject_context": finding.data_subject_context,
        "detection_confidence": finding.detection_confidence,
        "privacy_risk": finding.privacy_risk,
        "origin": finding.origin,
        "review_decision": finding.review_decision,
        "target": _target_projection(finding, source_lines),
        "action": layer.action,
        "effect": layer.effect,
        "effect_source": layer.effect_source,
        "enabled": layer.enabled,
    }
    if layer.effect is LayerEffect.BOX:
        projection["fill_color"] = layer.fill_color
    return projection


def _model_log_projection(log: ModelInteractionLog) -> dict[str, object]:
    return log.model_dump(mode="json", exclude={"debug"})


def build_audit_document(
    *,
    output: OutputSnapshot,
    source_path: Path,
    policy: InstructionPolicy,
    instruction_set_id: str,
    instruction_set_content_hash: str,
    events: list[PersistedAuditEvent],
    created_at: str,
) -> dict[str, object]:
    """Build one canonical audit document without source-derived prose."""
    source_lines = _plain_text_lines(output, source_path)
    last_event = events[-1]
    source = source_identity()
    return {
        "schema_version": 1,
        "application_version": application_version(),
        "source_revision": source.revision,
        "source_modified": source.modified,
        "session_id": output.session_id,
        "created_at": created_at,
        "source": fingerprint_file(output.source.file).model_dump(mode="json"),
        "output": {
            "file": output.file.filename,
            **fingerprint_file(output.file).model_dump(mode="json"),
        },
        "instruction_set": {
            "id": instruction_set_id,
            "content_hash": instruction_set_content_hash,
        },
        "analysis": {
            "calls": [_model_log_projection(log) for log in output.model_logs],
            "totals": {
                "input_tokens": sum(log.actual_input_tokens or 0 for log in output.model_logs),
                "output_tokens": sum(log.actual_output_tokens or 0 for log in output.model_logs),
                "reasoning_tokens": sum(log.reasoning_tokens or 0 for log in output.model_logs),
            },
        },
        "findings": [
            _layer_projection(layer, policy, source_lines) for layer in output.layers
        ],
        "events": events,
        "audit_boundary": {
            "last_event_id": last_event["event_id"],
            "last_event_hash": last_event["event_hash"],
        },
    }
