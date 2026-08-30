"""Native Anthropic Messages provider adapter."""

from __future__ import annotations

from typing import Any, cast

from app.adapters.anthropic.messages import AnthropicRequestBody, build_messages
from app.adapters.errors import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderModelNotFoundError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderTokenCountError,
    provider_request_id,
)
from app.errors import JsonValue
from app.inference.provider import (
    DetectionResponse,
    InputTokenCount,
    ModelMetadata,
    PreparedRequest,
    TokenConstraints,
    TokenCountMethod,
)
from app.inference.requests import DetectionRequest
from app.models.model import AnthropicMessagesSettings, ApiFormat

import anthropic


def _provider_error(error: Exception) -> ProviderError:
    request_id = provider_request_id(error)
    if isinstance(error, anthropic.RateLimitError):
        return ProviderRateLimitError(str(error), request_id)
    if isinstance(error, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return ProviderConnectionError(str(error), request_id=request_id)
    if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return ProviderAuthenticationError(
            str(error), getattr(error, "status_code", None), request_id
        )
    if isinstance(error, anthropic.NotFoundError):
        return ProviderModelNotFoundError(str(error), error.status_code, request_id)
    if isinstance(error, anthropic.APIStatusError):
        if error.status_code >= 500:
            return ProviderConnectionError(str(error), error.status_code, request_id)
        return ProviderRequestError(str(error), error.status_code, request_id)
    return ProviderRequestError(str(error), request_id=request_id)


class AnthropicProvider:
    """Task-scoped adapter for the native Anthropic Messages API."""

    api_format = ApiFormat.ANTHROPIC_MESSAGES

    def __init__(self, settings: AnthropicMessagesSettings) -> None:
        self._settings = settings
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.api_key,
            timeout=settings.timeout,
            max_retries=settings.max_retries,
        )
        self._metadata: ModelMetadata | None = None

    @property
    def model(self) -> str:
        return self._settings.model

    @property
    def requested_output_tokens(self) -> int | None:
        return self._settings.max_output_tokens

    async def model_metadata(self) -> ModelMetadata:
        if self._metadata is not None:
            return self._metadata
        try:
            model = await self._client.models.retrieve(self.model)
        except anthropic.AnthropicError as exc:
            raise _provider_error(exc) from exc
        self._metadata = ModelMetadata(
            provider_response=cast(dict[str, JsonValue], model.model_dump(mode="json")),
            model_id=model.id,
            display_name=model.display_name,
            max_input_tokens=model.max_input_tokens,
            max_output_tokens=model.max_tokens,
            default_temperature=None,
            max_temperature=None,
        )
        return self._metadata

    async def prepare(self, request: DetectionRequest) -> PreparedRequest:
        try:
            body, debug_payload = build_messages(request)
        except ValueError as exc:
            raise ProviderRequestError(str(exc)) from exc
        return PreparedRequest(body=body, debug_payload=debug_payload)

    async def constraints(self) -> TokenConstraints:
        metadata = await self.model_metadata()
        return TokenConstraints(
            context_window_tokens=None,
            max_input_tokens=metadata.max_input_tokens,
            max_output_tokens=metadata.max_output_tokens,
        )

    async def count_input_tokens(
        self,
        request: PreparedRequest,
    ) -> InputTokenCount:
        body = cast(AnthropicRequestBody, request.body)
        try:
            count = await self._client.messages.count_tokens(
                model=self.model,
                system=body.system,
                messages=cast(Any, body.messages),
            )
        except anthropic.AnthropicError as exc:
            normalized = _provider_error(exc)
            if isinstance(
                normalized,
                (ProviderAuthenticationError, ProviderRateLimitError, ProviderConnectionError),
            ):
                raise normalized from exc
            raise ProviderTokenCountError(str(exc)) from exc
        return InputTokenCount(tokens=count.input_tokens, method=TokenCountMethod.PROVIDER)

    async def generate(
        self,
        request: PreparedRequest,
        *,
        json_mode: bool,
    ) -> DetectionResponse:
        del json_mode
        body = cast(AnthropicRequestBody, request.body)
        if self.requested_output_tokens is None:
            raise ProviderRequestError("Anthropic Messages requires max_output_tokens")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "system": body.system,
            "messages": body.messages,
            "max_tokens": self.requested_output_tokens,
        }
        if self._settings.temperature is not None:
            kwargs["temperature"] = self._settings.temperature
        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.AnthropicError as exc:
            raise _provider_error(exc) from exc
        content = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        actual_input = response.usage.input_tokens
        actual_output = response.usage.output_tokens
        return DetectionResponse(
            content=content,
            model=response.model,
            finish_reason=response.stop_reason or "stop",
            actual_input_tokens=actual_input,
            actual_output_tokens=actual_output,
            total_tokens=actual_input + actual_output,
        )

    async def close(self) -> None:
        await self._client.close()
