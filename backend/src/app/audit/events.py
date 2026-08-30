"""Immutable facts awaiting append-only audit persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, Field, JsonValue, field_validator

_CONTENT_BEARING_KEYS = frozenset(
    {
        "custom_text",
        "description",
        "exact_text",
        "filename",
        "reason",
        "request_payload",
        "response_content",
        "reviewer_note",
        "stored_filename",
        "text",
    }
)


def _reject_content_bearing_keys(value: JsonValue) -> None:
    if isinstance(value, dict):
        forbidden = _CONTENT_BEARING_KEYS.intersection(value)
        if forbidden:
            names = ", ".join(sorted(forbidden))
            raise ValueError(f"audit payload contains content-bearing fields: {names}")
        for nested in value.values():
            _reject_content_bearing_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_content_bearing_keys(nested)


class ActorType(StrEnum):
    SYSTEM = "system"
    REVIEWER = "reviewer"


class AuditEventType(StrEnum):
    SESSION_CREATED = "session.created"
    SESSION_RENAMED = "session.renamed"
    FILE_UPLOADED = "file.uploaded"
    ANALYSIS_STARTED = "analysis.started"
    ANALYSIS_COMPLETED = "analysis.completed"
    ANALYSIS_FAILED = "analysis.failed"
    ANALYSIS_CANCELLED = "analysis.cancelled"
    REVIEW_FINDING_ADDED = "review.finding_added"
    REVIEW_FINDING_UPDATED = "review.finding_updated"
    REVIEW_LAYER_UPDATED = "review.layer_updated"
    REVIEW_EFFECT_RESET = "review.effect_reset"
    OUTPUT_RENDERED = "output.rendered"
    EXPORT_CREATED = "export.created"


ANALYSIS_STARTED: Final = AuditEventType.ANALYSIS_STARTED
ANALYSIS_COMPLETED: Final = AuditEventType.ANALYSIS_COMPLETED
ANALYSIS_FAILED: Final = AuditEventType.ANALYSIS_FAILED
ANALYSIS_CANCELLED: Final = AuditEventType.ANALYSIS_CANCELLED


class AuditEvent(BaseModel):
    """A durable fact before storage assigns its identity and hash."""

    session_id: str
    event_type: AuditEventType
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_id: str = "system"
    actor_type: ActorType = ActorType.SYSTEM

    @field_validator("payload")
    @classmethod
    def reject_content_bearing_fields(
        cls,
        payload: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        _reject_content_bearing_keys(payload)
        return payload

    model_config = {"extra": "forbid", "frozen": True}
