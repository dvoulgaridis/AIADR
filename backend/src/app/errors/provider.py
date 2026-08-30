"""Translate provider failures into stable application errors."""

from __future__ import annotations

from app.adapters.errors import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderModelNotFoundError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTokenCountError,
)
from app.errors import ApplicationError, ErrorCode, app_error
from app.models.model import ApiFormat

_ERROR_CODES: dict[type[ProviderError], ErrorCode] = {
    ProviderConnectionError: ErrorCode.PROVIDER_CONNECTION_FAILED,
    ProviderAuthenticationError: ErrorCode.PROVIDER_AUTHENTICATION_FAILED,
    ProviderRateLimitError: ErrorCode.PROVIDER_RATE_LIMITED,
    ProviderModelNotFoundError: ErrorCode.PROVIDER_MODEL_NOT_FOUND,
    ProviderRequestError: ErrorCode.PROVIDER_REQUEST_INVALID,
    ProviderTokenCountError: ErrorCode.TOKEN_COUNT_FAILED,
}


def from_provider_error(
    error: ProviderError,
    *,
    api_format: ApiFormat,
    model: str,
    model_log_id: str | None,
) -> ApplicationError:
    """Return a public error without forwarding provider response text."""
    return app_error(
        _ERROR_CODES[type(error)],
        details={
            "api_format": api_format,
            "provider_code": error.provider_code,
            "provider_status": error.status_code,
            "model": model,
            "model_log_id": model_log_id,
        },
    )
