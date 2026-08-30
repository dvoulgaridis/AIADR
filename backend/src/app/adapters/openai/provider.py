"""OpenAI-compatible Chat Completions provider adapter."""

from __future__ import annotations

from typing import Any, cast

from app.adapters.errors import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderError,
    ProviderModelNotFoundError,
    ProviderRateLimitError,
    ProviderRequestError,
    provider_request_id,
)
from app.adapters.openai.messages import OpenAIRequestBody, build_messages
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
from app.models.model import (
    ApiFormat,
    OpenAICompatibleSettings,
    OpenAIOutputTokenParameter,
)

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

_CHAT_FRAMING_TOKEN_RESERVE = 32


def _provider_error(error: Exception) -> ProviderError:
    request_id = provider_request_id(error)
    if isinstance(error, RateLimitError):
        return ProviderRateLimitError(str(error), request_id)
    if isinstance(error, APIConnectionError):
        return ProviderConnectionError(str(error), request_id=request_id)
    if isinstance(error, APIStatusError):
        if error.status_code in {401, 403}:
            return ProviderAuthenticationError(error.message, error.status_code, request_id)
        if error.status_code == 404:
            return ProviderModelNotFoundError(error.message, error.status_code, request_id)
        if error.status_code >= 500:
            return ProviderConnectionError(error.message, error.status_code, request_id)
        return ProviderRequestError(error.message, error.status_code, request_id)
    raise TypeError(f"Unsupported provider exception: {type(error).__name__}")


class OpenAIProvider:
    """Task-scoped adapter for OpenAI-compatible endpoints."""

    api_format = ApiFormat.OPENAI_COMPATIBLE

    def __init__(self, settings: OpenAICompatibleSettings) -> None:
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key or "sk-local",
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
        except APIStatusError as exc:
            raise _provider_error(exc) from exc
        except (RateLimitError, APIConnectionError) as exc:
            raise _provider_error(exc) from exc
        provider_response = cast(dict[str, JsonValue], model.model_dump(mode="json"))
        display_name = provider_response.get("display_name")
        self._metadata = ModelMetadata(
            provider_response=provider_response,
            model_id=model.id,
            display_name=display_name if isinstance(display_name, str) else None,
            max_input_tokens=None,
            max_output_tokens=None,
            default_temperature=None,
            max_temperature=None,
        )
        return self._metadata

    async def prepare(self, request: DetectionRequest) -> PreparedRequest:
        body = build_messages(request)
        return PreparedRequest(
            body=body,
            debug_payload=cast(dict[str, Any], {"messages": body.log_messages}),
        )

    async def constraints(self) -> TokenConstraints:
        return TokenConstraints(
            context_window_tokens=self._settings.context_window_tokens,
            max_input_tokens=None,
            max_output_tokens=None,
        )

    async def count_input_tokens(
        self,
        request: PreparedRequest,
    ) -> InputTokenCount:
        body = cast(OpenAIRequestBody, request.body)
        return InputTokenCount(
            tokens=body.text_byte_count + _CHAT_FRAMING_TOKEN_RESERVE,
            method=TokenCountMethod.ESTIMATED,
        )

    async def generate(
        self,
        request: PreparedRequest,
        *,
        json_mode: bool,
    ) -> DetectionResponse:
        body = cast(OpenAIRequestBody, request.body)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": body.messages,
        }
        if self.requested_output_tokens is not None:
            parameter = self._settings.output_token_parameter
            if parameter is OpenAIOutputTokenParameter.MAX_COMPLETION_TOKENS:
                kwargs["max_completion_tokens"] = self.requested_output_tokens
            else:
                kwargs["max_tokens"] = self.requested_output_tokens
        if self._settings.temperature is not None:
            kwargs["temperature"] = self._settings.temperature
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except (RateLimitError, APIConnectionError, APIStatusError) as exc:
            raise _provider_error(exc) from exc

        choice = response.choices[0]
        usage = response.usage
        completion_details = usage.completion_tokens_details if usage else None
        return DetectionResponse(
            content=choice.message.content or "",
            model=response.model,
            finish_reason=choice.finish_reason or "stop",
            actual_input_tokens=usage.prompt_tokens if usage else None,
            actual_output_tokens=usage.completion_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            reasoning_tokens=(
                completion_details.reasoning_tokens if completion_details is not None else None
            ),
        )

    async def close(self) -> None:
        await self._client.close()
