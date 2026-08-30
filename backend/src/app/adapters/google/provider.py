"""Native Google Gen AI generateContent provider adapter."""

from __future__ import annotations

from typing import Any, cast

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
from app.adapters.google.contents import GoogleRequestBody, build_contents
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
from app.models.model import ApiFormat, GoogleGenAISettings

from google import genai
from google.genai import errors as google_errors
from google.genai import types


def _provider_error(error: Exception) -> ProviderError:
    status_code = getattr(error, "code", None)
    request_id = provider_request_id(error)
    if status_code in {401, 403}:
        return ProviderAuthenticationError(str(error), status_code, request_id)
    if status_code == 404:
        return ProviderModelNotFoundError(str(error), status_code, request_id)
    if status_code == 429:
        return ProviderRateLimitError(str(error), request_id)
    if status_code is not None and status_code >= 500:
        return ProviderConnectionError(str(error), status_code, request_id)
    if status_code is not None:
        return ProviderRequestError(str(error), status_code, request_id)
    return ProviderConnectionError(str(error), request_id=request_id)


class GoogleProvider:
    """Task-scoped adapter for Google Gen AI."""

    api_format = ApiFormat.GOOGLE_GENAI

    def __init__(self, settings: GoogleGenAISettings) -> None:
        self._settings = settings
        retry_options = types.HttpRetryOptions(attempts=settings.max_retries + 1)
        http_options = types.HttpOptions(
            timeout=round(settings.timeout * 1000),
            retry_options=retry_options,
        )
        self._client = genai.Client(api_key=settings.api_key, http_options=http_options)
        self._model_metadata: dict[str, types.Model] = {}

    @property
    def model(self) -> str:
        return self._settings.model

    @property
    def requested_output_tokens(self) -> int | None:
        return self._settings.max_output_tokens

    async def prepare(self, request: DetectionRequest) -> PreparedRequest:
        body, debug_payload = build_contents(request)
        return PreparedRequest(body=body, debug_payload=debug_payload)

    async def _model(self, model: str) -> types.Model:
        cached = self._model_metadata.get(model)
        if cached is not None:
            return cached
        try:
            metadata = await self._client.aio.models.get(model=model)
        except google_errors.APIError as exc:
            raise _provider_error(exc) from exc
        if metadata.supported_actions and "generateContent" not in metadata.supported_actions:
            raise ProviderRequestError(
                f"Model {model} does not advertise generateContent support"
            )
        self._model_metadata[model] = metadata
        return metadata

    async def model_metadata(self) -> ModelMetadata:
        metadata = await self._model(self.model)
        return ModelMetadata(
            provider_response=cast(dict[str, JsonValue], metadata.model_dump(mode="json")),
            model_id=metadata.name or self.model,
            display_name=metadata.display_name,
            max_input_tokens=metadata.input_token_limit,
            max_output_tokens=metadata.output_token_limit,
            default_temperature=metadata.temperature,
            max_temperature=metadata.max_temperature,
        )

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
        body = cast(GoogleRequestBody, request.body)
        try:
            result = await self._client.aio.models.count_tokens(
                model=self.model,
                contents=cast(Any, [body.system_instruction, *body.contents]),
            )
        except (TypeError, ValueError) as exc:
            raise ProviderTokenCountError(str(exc)) from exc
        except google_errors.APIError as exc:
            normalized = _provider_error(exc)
            if isinstance(
                normalized,
                (ProviderAuthenticationError, ProviderRateLimitError, ProviderConnectionError),
            ):
                raise normalized from exc
            raise ProviderTokenCountError(str(exc)) from exc
        if result.total_tokens is None:
            raise ProviderTokenCountError("Google returned no input token count")
        return InputTokenCount(tokens=result.total_tokens, method=TokenCountMethod.PROVIDER)

    async def generate(
        self,
        request: PreparedRequest,
        *,
        json_mode: bool,
    ) -> DetectionResponse:
        body = cast(GoogleRequestBody, request.body)
        metadata = await self._model(self.model)
        temperature = self._settings.temperature
        if (
            temperature is not None
            and metadata.max_temperature is not None
            and temperature > metadata.max_temperature
        ):
            raise ProviderRequestError(
                f"Temperature exceeds the model maximum of {metadata.max_temperature}"
            )
        try:
            config = types.GenerateContentConfig(
                system_instruction=body.system_instruction,
                max_output_tokens=self.requested_output_tokens,
                temperature=temperature,
                response_mime_type="application/json" if json_mode else None,
            )
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=cast(Any, body.contents),
                config=config,
            )
        except (TypeError, ValueError) as exc:
            raise ProviderRequestError(str(exc)) from exc
        except google_errors.APIError as exc:
            raise _provider_error(exc) from exc
        usage = response.usage_metadata
        candidate = response.candidates[0] if response.candidates else None
        finish_reason = getattr(candidate, "finish_reason", None)
        return DetectionResponse(
            content=response.text or "",
            model=self.model,
            finish_reason=str(finish_reason or "stop"),
            actual_input_tokens=usage.prompt_token_count if usage else None,
            actual_output_tokens=usage.candidates_token_count if usage else None,
            total_tokens=usage.total_token_count if usage else None,
            reasoning_tokens=usage.thoughts_token_count if usage else None,
        )

    async def close(self) -> None:
        await self._client.aio.aclose()
