"""Resolve persisted models into complete provider settings."""

from __future__ import annotations

from typing import assert_never

from app.errors import ErrorCode, app_error
from app.models.model import (
    AnthropicMessagesSettings,
    GoogleGenAISettings,
    Model,
    ModelSettings,
    OpenAICompatibleSettings,
)


def model_is_configured(settings: ModelSettings) -> bool:
    """Return whether a model has all values required by its API format."""
    match settings.provider:
        case OpenAICompatibleSettings():
            return bool(
                settings.provider.base_url
                and settings.provider.model
                and settings.provider.context_window_tokens is not None
            )
        case AnthropicMessagesSettings():
            return bool(
                settings.provider.api_key
                and settings.provider.model
                and settings.provider.max_output_tokens is not None
            )
        case GoogleGenAISettings():
            return bool(settings.provider.api_key and settings.provider.model)
        case unexpected:
            assert_never(unexpected)


def model_endpoint_is_configured(settings: ModelSettings) -> bool:
    """Return whether a model identifies a model endpoint for metadata inspection."""
    match settings.provider:
        case OpenAICompatibleSettings():
            return bool(settings.provider.base_url and settings.provider.model)
        case AnthropicMessagesSettings() | GoogleGenAISettings():
            return bool(settings.provider.api_key and settings.provider.model)
        case unexpected:
            assert_never(unexpected)


def require_configured_model(model: Model) -> Model:
    """Return a complete model or raise the shared configuration error."""
    if not model.configured or not model_is_configured(model):
        raise app_error(
            ErrorCode.MODEL_ENDPOINT_NOT_CONFIGURED,
            details={"model_id": model.model_id, "api_format": model.provider.api_format},
        )
    return model
