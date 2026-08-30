"""Stable facade for AIADR application errors."""

from app.errors.exceptions import ApplicationError, app_error
from app.errors.types import ErrorCategory, ErrorCode, ErrorDetails, JsonValue

__all__ = [
    "ApplicationError",
    "ErrorCategory",
    "ErrorCode",
    "ErrorDetails",
    "JsonValue",
    "app_error",
]
