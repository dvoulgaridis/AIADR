"""Audit-event projections for the HTTP boundary."""

from app.api.contracts import AuditEvent
from app.audit.event_log import PersistedAuditEvent


def to_api_audit_event(event: PersistedAuditEvent) -> AuditEvent:
    """Validate one stored audit event for public serialization."""
    return AuditEvent.model_validate(event)
