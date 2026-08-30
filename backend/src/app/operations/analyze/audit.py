"""Durable audit facts produced by analysis operations."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue

from app.audit.events import (
    ANALYSIS_CANCELLED,
    ANALYSIS_COMPLETED,
    ANALYSIS_FAILED,
    ANALYSIS_STARTED,
    AuditEvent,
)
from app.errors import ApplicationError
from app.sessions.records import SessionRecord
from app.sources.kinds import SourceKind


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Stable identifiers shared by durable analysis facts."""

    session_id: str
    source_kind: SourceKind
    model_id: str
    model: str
    instruction_set_id: str
    instruction_set_content_hash: str


def _context_payload(context: AnalysisContext) -> dict[str, JsonValue]:
    return {
        "kind": context.source_kind,
        "model_id": context.model_id,
        "model": context.model,
        "instruction_set_id": context.instruction_set_id,
        "instruction_set_content_hash": context.instruction_set_content_hash,
    }


def analysis_started(context: AnalysisContext) -> AuditEvent:
    """Return the fact that analysis began with resolved inputs."""
    return AuditEvent(
        session_id=context.session_id,
        event_type=ANALYSIS_STARTED,
        payload=_context_payload(context),
    )


def analysis_completed(
    context: AnalysisContext,
    *,
    finding_count: int,
    layer_count: int,
    rejected_count: int,
    page_count: int | None,
) -> AuditEvent:
    """Return the fact that analysis completed successfully."""
    return AuditEvent(
        session_id=context.session_id,
        event_type=ANALYSIS_COMPLETED,
        payload={
            **_context_payload(context),
            "finding_count": finding_count,
            "layer_count": layer_count,
            "rejected_count": rejected_count,
            "page_count": page_count,
        },
    )


def analysis_setup_failed(
    *,
    session: SessionRecord,
    error: ApplicationError,
) -> AuditEvent:
    """Return a setup failure without inventing unresolved identities."""
    return AuditEvent(
        session_id=session.session_id,
        event_type=ANALYSIS_FAILED,
        payload={
            "phase": "setup",
            "kind": session.source.kind,
            "error_code": error.code.value,
            "error_category": error.category.value,
            "retryable": error.retryable,
            "correlation_id": error.correlation_id,
        },
    )


def analysis_failed(context: AnalysisContext, error: ApplicationError) -> AuditEvent:
    """Return the fact that an owned analysis attempt failed."""
    return AuditEvent(
        session_id=context.session_id,
        event_type=ANALYSIS_FAILED,
        payload={
            **_context_payload(context),
            "error_code": error.code.value,
            "error_category": error.category.value,
            "retryable": error.retryable,
            "correlation_id": error.correlation_id,
        },
    )


def analysis_cancelled(context: AnalysisContext) -> AuditEvent:
    """Return the fact that an owned analysis attempt was cancelled."""
    return AuditEvent(
        session_id=context.session_id,
        event_type=ANALYSIS_CANCELLED,
        payload=_context_payload(context),
    )
