"""Runtime application-error occurrences."""

from __future__ import annotations

from app.core.ids import new_correlation_id
from app.errors.catalog import ERROR_SPECS
from app.errors.types import ErrorCategory, ErrorCode, ErrorDetails


class ApplicationError(Exception):
    """One occurrence of a catalogued application failure."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        message: str | None = None,
        details: ErrorDetails | None = None,
        correlation_id: str | None = None,
    ) -> None:
        spec = ERROR_SPECS[code]
        self.code = code
        self.message = message if message is not None else spec.message
        self.category: ErrorCategory = spec.category
        self.retryable = spec.retryable
        self.details = details
        self.correlation_id = correlation_id or new_correlation_id()
        super().__init__(self.message)


def app_error(
    code: ErrorCode,
    *,
    message: str | None = None,
    details: ErrorDetails | None = None,
) -> ApplicationError:
    """Construct an application error from its stable catalog identity."""
    return ApplicationError(code, message=message, details=details)
