"""Model and dependency projections for the HTTP boundary."""

from app.adapters.libreoffice import LibreOfficeStatus
from app.api.contracts import DependencyStatus as ApiDependencyStatus
from app.api.contracts import Model as ApiModel
from app.api.contracts import ModelMetadata as ApiModelMetadata
from app.api.contracts import ModelWriteRequest
from app.inference.provider import ModelMetadata
from app.models.model import Model, ModelSettings
from app.sources.audio import FFmpegStatus


def to_model_settings(
    request: ModelWriteRequest,
    existing: Model | None,
) -> ModelSettings:
    """Map a write request while preserving an omitted stored API key."""
    values = request.model_dump()
    provider = values["provider"]
    requested_api_key = provider.pop("api_key")
    provider["api_key"] = (
        existing.provider.api_key
        if (
            requested_api_key is None
            and existing is not None
            and existing.provider.api_format == provider["api_format"]
        )
        else (requested_api_key or "")
    )
    return ModelSettings.model_validate(values)


def to_api_model(model: Model) -> ApiModel:
    """Project one persisted model without exposing its saved API key."""
    provider = model.provider.model_dump(exclude={"api_key"}, mode="json")
    provider["api_key_configured"] = bool(model.provider.api_key)
    return ApiModel.model_validate(
        {
            "model_id": model.model_id,
            "label": model.label,
            "provider": provider,
            "capabilities": model.capabilities.model_dump(mode="json"),
            "configured": model.configured,
        }
    )


def to_api_model_metadata(metadata: ModelMetadata) -> ApiModelMetadata:
    """Project the provider's model response without reshaping it."""
    return ApiModelMetadata.model_validate(metadata.provider_response)


def to_api_dependency_status(
    status: FFmpegStatus | LibreOfficeStatus,
) -> ApiDependencyStatus:
    """Project dependency availability and its detected executable path."""
    return ApiDependencyStatus(
        available=status.available,
        path=status.path,
        version=status.version,
        error=status.error,
    )
