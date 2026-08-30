"""Task-scoped provider-neutral detection and model diagnostics."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from types import TracebackType
from typing import Self, assert_never

from app.adapters.anthropic import AnthropicProvider
from app.adapters.errors import ProviderError
from app.adapters.google import GoogleProvider
from app.adapters.openai import OpenAIProvider
from app.core.ids import new_model_log_id
from app.core.runtime import sensitive_debug_enabled
from app.errors import ApplicationError, ErrorCode, JsonValue, app_error
from app.errors.provider import from_provider_error
from app.inference.model_log import (
    DebugModelIO,
    ModelInteractionLog,
    ModelInteractionStatus,
    ModelResultSummary,
    ParseStatus,
)
from app.inference.provider import (
    DetectionProvider,
    InputTokenCount,
    ModelMetadata,
    TokenBudget,
    TokenConstraints,
    TokenCountMethod,
)
from app.inference.requests import BinaryAttachment, DetectionRequest, summarize_request
from app.inference.token_budget import maximum_input_tokens, validate_token_budget
from app.models.model import (
    AnthropicMessagesSettings,
    GoogleGenAISettings,
    Model,
    OpenAICompatibleSettings,
)
from app.models.settings import model_endpoint_is_configured, require_configured_model
from app.sources.kinds import SourceKind
from app.storage.model_log_store import upsert_log


@dataclass(frozen=True, slots=True)
class ModelCallContext:
    session_id: str
    kind: SourceKind
    page: int | None = None


@dataclass(frozen=True, slots=True)
class DetectionOutput:
    """Ephemeral provider content linked to its durable metadata log."""

    log_id: str
    content: str


def _provider_for(model: Model) -> DetectionProvider:
    match model.provider:
        case OpenAICompatibleSettings() as settings:
            return OpenAIProvider(settings)
        case AnthropicMessagesSettings() as settings:
            return AnthropicProvider(settings)
        case GoogleGenAISettings() as settings:
            return GoogleProvider(settings)
        case unexpected:
            assert_never(unexpected)


async def inspect_model(model: Model) -> ModelMetadata:
    """Return endpoint-reported metadata without requiring generation limits."""
    if not model_endpoint_is_configured(model):
        raise app_error(ErrorCode.MODEL_ENDPOINT_NOT_CONFIGURED)
    provider = _provider_for(model)
    try:
        return await provider.model_metadata()
    except ProviderError as exc:
        raise from_provider_error(
            exc,
            api_format=provider.api_format,
            model=provider.model,
            model_log_id=None,
        ) from exc
    finally:
        await provider.close()


def _completed_log(
    log: ModelInteractionLog,
    *,
    status: ModelInteractionStatus,
    started: float,
    **updates: object,
) -> ModelInteractionLog:
    return log.model_copy(
        update={
            "status": status,
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_ms": max(0, round((monotonic() - started) * 1000)),
            **updates,
        }
    )


def _budget_fields(
    count: InputTokenCount,
    constraints: TokenConstraints,
    budget: TokenBudget | None,
) -> dict[str, object]:
    return {
        "input_count_method": count.method,
        "estimated_input_tokens": (
            count.tokens if count.method is TokenCountMethod.ESTIMATED else None
        ),
        "provider_counted_input_tokens": (
            count.tokens if count.method is TokenCountMethod.PROVIDER else None
        ),
        "requested_output_tokens": (
            budget.requested_output_tokens if budget is not None else None
        ),
        "max_input_tokens": constraints.max_input_tokens,
    }


def _debug_error(log: ModelInteractionLog, message: str) -> DebugModelIO | None:
    if log.debug is None:
        return None
    return log.debug.model_copy(update={"error_message": message})


class DetectionSession:
    """Own one provider client and connection check for one analysis task."""

    def __init__(self, model: Model) -> None:
        self._model = require_configured_model(model)
        self._provider = _provider_for(self._model)
        self._connection_checked = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._provider.close()

    async def _check_connection(self) -> None:
        if self._connection_checked:
            return
        try:
            await self._provider.model_metadata()
        except ProviderError as exc:
            raise from_provider_error(
                exc,
                api_format=self._provider.api_format,
                model=self._provider.model,
                model_log_id=None,
            ) from exc
        self._connection_checked = True

    async def _detect(
        self,
        *,
        context: ModelCallContext,
        request: DetectionRequest,
    ) -> DetectionOutput:
        await self._check_connection()
        requested_output = self._provider.requested_output_tokens

        try:
            prepared = await self._provider.prepare(request)
        except ProviderError as exc:
            raise from_provider_error(
                exc,
                api_format=self._provider.api_format,
                model=self._provider.model,
                model_log_id=None,
            ) from exc

        log_id = new_model_log_id()
        log = ModelInteractionLog(
            log_id=log_id,
            session_id=context.session_id,
            created_at=datetime.now(UTC).isoformat(),
            status=ModelInteractionStatus.STARTED,
            kind=context.kind,
            page=context.page,
            api_format=self._provider.api_format,
            model=self._provider.model,
            request_summary=summarize_request(request),
            debug=(
                DebugModelIO(
                    request_payload={
                        **prepared.debug_payload,
                        "model": self._provider.model,
                        "requested_output_tokens": requested_output,
                        "json_mode": self._model.capabilities.supports_json_mode,
                    }
                )
                if sensitive_debug_enabled()
                else None
            ),
            requested_output_tokens=requested_output,
        )
        upsert_log(log)
        started = monotonic()

        try:
            constraints = await self._provider.constraints()
            count = await self._provider.count_input_tokens(prepared)
            budget = validate_token_budget(
                count,
                constraints,
                requested_output_tokens=requested_output,
            )
            log = log.model_copy(update=_budget_fields(count, constraints, budget))
            upsert_log(log)
            response = await self._provider.generate(
                prepared,
                json_mode=self._model.capabilities.supports_json_mode,
            )
        except asyncio.CancelledError:
            upsert_log(
                _completed_log(
                    log,
                    status=ModelInteractionStatus.CANCELLED,
                    started=started,
                    result_summary=log.result_summary.model_copy(
                        update={"parse_status": ParseStatus.NOT_APPLICABLE}
                    ),
                )
            )
            raise
        except ProviderError as exc:
            upsert_log(
                _completed_log(
                    log,
                    status=ModelInteractionStatus.FAILED,
                    started=started,
                    result_summary=ModelResultSummary(
                        parse_status=ParseStatus.NOT_APPLICABLE,
                        provider_code=exc.provider_code,
                        provider_status=exc.status_code,
                        provider_request_id=exc.request_id,
                        provider_retryable=exc.retryable,
                    ),
                    debug=_debug_error(log, exc.diagnostic_message),
                )
            )
            raise from_provider_error(
                exc,
                api_format=self._provider.api_format,
                model=self._provider.model,
                model_log_id=log_id,
            ) from exc
        except ApplicationError as exc:
            upsert_log(
                _completed_log(
                    log,
                    status=ModelInteractionStatus.FAILED,
                    started=started,
                    result_summary=log.result_summary.model_copy(
                        update={"parse_status": ParseStatus.NOT_APPLICABLE}
                    ),
                    debug=_debug_error(log, exc.message),
                )
            )
            raise
        except Exception as exc:
            upsert_log(
                _completed_log(
                    log,
                    status=ModelInteractionStatus.FAILED,
                    started=started,
                    result_summary=log.result_summary.model_copy(
                        update={"parse_status": ParseStatus.NOT_APPLICABLE}
                    ),
                    debug=_debug_error(log, str(exc)),
                )
            )
            raise

        upsert_log(
            _completed_log(
                log,
                status=ModelInteractionStatus.SUCCEEDED,
                started=started,
                result_summary=log.result_summary.model_copy(
                    update={"response_size_bytes": len(response.content.encode("utf-8"))}
                ),
                debug=(
                    log.debug.model_copy(update={"response_content": response.content})
                    if log.debug
                    else None
                ),
                finish_reason=response.finish_reason,
                actual_input_tokens=response.actual_input_tokens,
                actual_output_tokens=response.actual_output_tokens,
                total_tokens=response.total_tokens,
                reasoning_tokens=response.reasoning_tokens,
            )
        )
        return DetectionOutput(log_id=log_id, content=response.content)

    async def detect_text(
        self,
        *,
        context: ModelCallContext,
        system_prompt: str,
        source_payload: Mapping[str, JsonValue],
    ) -> DetectionOutput:
        return await self._detect(
            context=context,
            request=DetectionRequest(
                system_prompt=system_prompt,
                source_payload=source_payload,
            ),
        )

    async def detect_vision(
        self,
        *,
        context: ModelCallContext,
        system_prompt: str,
        source_payload: Mapping[str, JsonValue],
        image_bytes: bytes,
        mime_type: str,
    ) -> DetectionOutput:
        if not self._model.capabilities.supports_vision:
            raise app_error(
                ErrorCode.VISION_NOT_SUPPORTED,
                details={"model_id": self._model.model_id, "model": self.model},
            )
        return await self._detect(
            context=context,
            request=DetectionRequest(
                system_prompt=system_prompt,
                source_payload=source_payload,
                attachment=BinaryAttachment(
                    kind=SourceKind.IMAGE,
                    mime_type=mime_type,
                    data=image_bytes,
                ),
            ),
        )

    async def detect_audio(
        self,
        *,
        context: ModelCallContext,
        system_prompt: str,
        source_payload: Mapping[str, JsonValue],
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
    ) -> DetectionOutput:
        if not self._model.capabilities.supports_audio:
            raise app_error(
                ErrorCode.AUDIO_NOT_SUPPORTED,
                details={"model_id": self._model.model_id, "model": self.model},
            )
        return await self._detect(
            context=context,
            request=DetectionRequest(
                system_prompt=system_prompt,
                source_payload=source_payload,
                attachment=BinaryAttachment(
                    kind=SourceKind.AUDIO,
                    mime_type=mime_type,
                    data=audio_bytes,
                ),
            ),
        )

    @property
    def model(self) -> str:
        return self._provider.model

    async def source_payload_byte_budget(self, system_prompt: str) -> int | None:
        """Return a conservative text batching budget from selected-model limits."""
        await self._check_connection()
        requested_output = self._provider.requested_output_tokens
        constraints = await self._provider.constraints()
        input_limit = maximum_input_tokens(
            constraints,
            requested_output_tokens=requested_output,
        )
        if input_limit is None:
            return None
        available = input_limit - len(system_prompt.encode()) - 512
        if available <= 0:
            raise app_error(
                ErrorCode.MODEL_INPUT_LIMIT_EXCEEDED,
                details={
                    "max_input_tokens": input_limit,
                },
            )
        return available
