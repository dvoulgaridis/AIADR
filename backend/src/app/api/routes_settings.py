"""API routes for application settings."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.adapters.libreoffice import libreoffice_status
from app.api.contracts import (
    DependenciesResponse as ApiDependenciesResponse,
)
from app.api.contracts import (
    ModelMetadata as ApiModelMetadata,
)
from app.api.contracts import (
    ModelsResponse as ApiModelsResponse,
)
from app.api.contracts import (
    ModelWriteRequest,
    ReviewOptions,
)
from app.api.mappers.models import (
    to_api_dependency_status,
    to_api_model,
    to_api_model_metadata,
    to_model_settings,
)
from app.domain.layer import SUPPORTED_EFFECTS_BY_KIND_AND_ACTION
from app.inference.detection import inspect_model
from app.models.model import Model
from app.models.store import (
    activate_model,
    delete_model,
    find_model,
    get_active_model_id,
    get_model,
    list_models,
    save_model,
)
from app.sources.audio import ffmpeg_status

router = APIRouter(tags=["settings"])


@router.get("/settings/models")
async def list_models_route() -> ApiModelsResponse:
    """Return saved models."""
    return ApiModelsResponse(
        models=[to_api_model(model) for model in list_models()],
        active_model_id=get_active_model_id(),
    )


@router.get("/settings/dependencies")
def get_dependencies() -> ApiDependenciesResponse:
    """Return the current availability of local media dependencies."""
    return ApiDependenciesResponse(
        ffmpeg=to_api_dependency_status(ffmpeg_status()),
        libreoffice=to_api_dependency_status(libreoffice_status()),
    )


@router.put(
    "/settings/models/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_update_model(
    model_id: str,
    model: ModelWriteRequest,
) -> Response:
    """Create or update a saved model."""
    settings = to_model_settings(model, find_model(model_id))
    save_model(
        Model(model_id=model_id, **settings.model_dump()),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/settings/models/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_delete_model(model_id: str) -> Response:
    """Delete a saved model."""
    delete_model(model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/settings/models/{model_id}/model-metadata")
async def get_model_model_metadata_route(model_id: str) -> ApiModelMetadata:
    """Return provider-reported metadata for one saved model."""
    return to_api_model_metadata(await inspect_model(get_model(model_id)))


@router.put(
    "/settings/models/{model_id}/active",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_activate_model(model_id: str) -> Response:
    """Select a saved model for future analysis."""
    activate_model(model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/settings/review-options")
async def get_review_options_route() -> ReviewOptions:
    """Return application-owned review decisions and redaction effects."""
    return ReviewOptions.model_validate(
        {
            "review_decisions": ["needs_review", "confirmed", "preserved"],
            "supported_effects_by_kind_and_action": SUPPORTED_EFFECTS_BY_KIND_AND_ACTION,
        }
    )
