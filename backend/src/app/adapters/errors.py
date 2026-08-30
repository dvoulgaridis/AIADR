"""Transport-neutral provider failures used at the inference boundary."""

from __future__ import annotations


def provider_request_id(error: Exception) -> str | None:
    """Return a native request identifier only when it is already textual."""
    value = getattr(error, "request_id", None)
    return value if isinstance(value, str) else None


class ProviderError(Exception):
    """Normalized provider failure containing diagnostics safe for local logs."""

    def __init__(
        self,
        diagnostic_message: str,
        *,
        provider_code: str,
        retryable: bool = False,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(diagnostic_message)
        self.diagnostic_message = diagnostic_message
        self.provider_code = provider_code
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id


class ProviderConnectionError(ProviderError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            provider_code=f"http_{status_code}" if status_code is not None else "connection_error",
            retryable=True,
            status_code=status_code,
            request_id=request_id,
        )


class ProviderAuthenticationError(ProviderError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            provider_code="authentication_error",
            status_code=status_code,
            request_id=request_id,
        )


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str, request_id: str | None = None) -> None:
        super().__init__(
            message,
            provider_code="rate_limit",
            retryable=True,
            status_code=429,
            request_id=request_id,
        )


class ProviderModelNotFoundError(ProviderError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            provider_code="model_not_found",
            status_code=status_code,
            request_id=request_id,
        )


class ProviderRequestError(ProviderError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(
            message,
            provider_code=f"http_{status_code}" if status_code is not None else "invalid_request",
            retryable=status_code is not None and status_code >= 500,
            status_code=status_code,
            request_id=request_id,
        )


class ProviderTokenCountError(ProviderError):
    def __init__(self, message: str) -> None:
        super().__init__(message, provider_code="token_count_failed", retryable=True)
