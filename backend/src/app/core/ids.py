"""Prefixed ULID generation utilities."""

from __future__ import annotations

from ulid import ULID


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def new_session_id() -> str:
    """Generate a new session ID."""
    return _new_id("s")


def new_model_id() -> str:
    """Generate a new model ID."""
    return _new_id("m")


def new_layer_id() -> str:
    """Generate a new layer ID."""
    return _new_id("l")


def new_finding_id() -> str:
    """Generate a new finding ID."""
    return _new_id("f")


def new_event_id() -> str:
    """Generate a new audit event ID."""
    return _new_id("evt")


def new_model_log_id() -> str:
    """Generate a new model interaction log ID."""
    return _new_id("ml")


def new_export_id() -> str:
    """Generate a new export record ID."""
    return _new_id("exp")


def new_correlation_id() -> str:
    """Generate a new correlation ID for request tracing."""
    return _new_id("corr")
