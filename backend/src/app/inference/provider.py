"""Provider-neutral detection contracts consumed by inference."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.errors import JsonValue
from app.inference.requests import DetectionRequest
from app.models.model import ApiFormat


class TokenCountMethod(StrEnum):
    """How the pre-generation input count was obtained."""

    PROVIDER = "provider"
    ESTIMATED = "estimated"


@dataclass(frozen=True, slots=True)
class InputTokenCount:
    tokens: int
    method: TokenCountMethod


@dataclass(frozen=True, slots=True)
class TokenConstraints:
    context_window_tokens: int | None
    max_input_tokens: int | None
    max_output_tokens: int | None


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    """Provider-reported information about one selected model."""

    provider_response: dict[str, JsonValue]
    model_id: str
    display_name: str | None
    max_input_tokens: int | None
    max_output_tokens: int | None
    default_temperature: float | None
    max_temperature: float | None


@dataclass(frozen=True, slots=True)
class TokenBudget:
    input_tokens: int
    input_count_method: TokenCountMethod
    requested_output_tokens: int | None


@dataclass(frozen=True, slots=True)
class PreparedRequest:
    """Provider-owned wire value paired with development diagnostics."""

    body: object
    debug_payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class DetectionResponse:
    """Provider response normalized for extraction and diagnostics."""

    content: str
    model: str
    finish_reason: str
    actual_input_tokens: int | None
    actual_output_tokens: int | None
    total_tokens: int | None
    reasoning_tokens: int | None = None


class DetectionProvider(Protocol):
    """Operations required from one task-scoped provider adapter."""

    api_format: ApiFormat

    @property
    def model(self) -> str: ...

    @property
    def requested_output_tokens(self) -> int | None: ...

    async def model_metadata(self) -> ModelMetadata: ...

    async def prepare(self, request: DetectionRequest) -> PreparedRequest: ...

    async def constraints(self) -> TokenConstraints: ...

    async def count_input_tokens(
        self,
        request: PreparedRequest,
    ) -> InputTokenCount: ...

    async def generate(
        self,
        request: PreparedRequest,
        *,
        json_mode: bool,
    ) -> DetectionResponse: ...

    async def close(self) -> None: ...
