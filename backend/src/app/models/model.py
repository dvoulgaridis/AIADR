"""Persisted analysis model contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field, field_validator, model_validator


class ApiFormat(StrEnum):
    """Supported provider wire formats."""

    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GOOGLE_GENAI = "google_genai"


class OpenAIOutputTokenParameter(StrEnum):
    """OpenAI-compatible field used for the requested output ceiling."""

    MAX_TOKENS = "max_tokens"
    MAX_COMPLETION_TOKENS = "max_completion_tokens"


class ModelCapabilities(BaseModel):
    """User-confirmed capabilities of one configured model."""

    supports_vision: bool = False
    supports_audio: bool = False
    supports_json_mode: bool = False

    model_config = {"extra": "forbid", "frozen": True}


class OpenAICompatibleSettings(BaseModel):
    """Complete settings for a Chat Completions-compatible API."""

    api_format: Literal[ApiFormat.OPENAI_COMPATIBLE] = ApiFormat.OPENAI_COMPATIBLE
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    context_window_tokens: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=128)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    timeout: float = Field(default=120.0, ge=1.0)
    max_retries: int = Field(default=1, ge=0, le=5)
    output_token_parameter: OpenAIOutputTokenParameter = OpenAIOutputTokenParameter.MAX_TOKENS

    @model_validator(mode="after")
    def validate_token_limits(self) -> OpenAICompatibleSettings:
        if (
            self.context_window_tokens is not None
            and self.max_output_tokens is not None
            and self.max_output_tokens >= self.context_window_tokens
        ):
            raise ValueError("Max output tokens must be lower than the context window")
        return self

    model_config = {"extra": "forbid", "frozen": True}


class AnthropicMessagesSettings(BaseModel):
    """Complete settings for the Anthropic Messages API."""

    api_format: Literal[ApiFormat.ANTHROPIC_MESSAGES] = ApiFormat.ANTHROPIC_MESSAGES
    api_key: str = ""
    model: str = ""
    max_output_tokens: int | None = Field(default=None, ge=128)
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)
    timeout: float = Field(default=120.0, ge=1.0)
    max_retries: int = Field(default=1, ge=0, le=5)

    model_config = {"extra": "forbid", "frozen": True}


class GoogleGenAISettings(BaseModel):
    """Complete settings for the Google Gen AI API."""

    api_format: Literal[ApiFormat.GOOGLE_GENAI] = ApiFormat.GOOGLE_GENAI
    api_key: str = ""
    model: str = ""
    max_output_tokens: int | None = Field(default=None, ge=128)
    temperature: float | None = Field(default=None, ge=0.0)
    timeout: float = Field(default=120.0, ge=1.0)
    max_retries: int = Field(default=1, ge=0, le=5)

    model_config = {"extra": "forbid", "frozen": True}


ProviderSettings: TypeAlias = Annotated[
    OpenAICompatibleSettings | AnthropicMessagesSettings | GoogleGenAISettings,
    Field(discriminator="api_format"),
]


class ModelSettings(BaseModel):
    """Editable settings for one saved analysis model."""

    label: str = Field(min_length=1)
    provider: ProviderSettings = Field(default_factory=OpenAICompatibleSettings)
    capabilities: ModelCapabilities = Field(default_factory=ModelCapabilities)
    configured: bool = False

    @field_validator("label")
    @classmethod
    def validate_label(cls, label: str) -> str:
        normalized = label.strip()
        if not normalized:
            raise ValueError("Model label is required")
        return normalized

    @model_validator(mode="after")
    def validate_capabilities(self) -> ModelSettings:
        if isinstance(self.provider, AnthropicMessagesSettings):
            if self.capabilities.supports_audio:
                raise ValueError("Anthropic Messages audio attachments are not supported")
            if self.capabilities.supports_json_mode:
                raise ValueError("Anthropic Messages does not enforce JSON mode")
        return self

    model_config = {"extra": "forbid"}


class Model(ModelSettings):
    """A saved AI analysis model."""

    model_id: str = Field(default="", description="Stable local model ID.")
