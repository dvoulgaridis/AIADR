"""API routes for findings, layers, and reviewer choices."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.contracts import (
    ClassificationOption,
    ClassificationOptionsResponse,
    FindingUpdateRequest,
    LayersResponse,
    LayerUpdateRequest,
    ManualFindingCreateRequest,
)
from app.api.mappers.layers import to_api_layer
from app.api.validation import require_non_empty_patch
from app.operations import review as review_operations
from app.storage import review_store, session_store

router = APIRouter(tags=["review"])


@router.post(
    "/sessions/{session_id}/findings",
    status_code=status.HTTP_201_CREATED,
)
async def request_add_finding(session_id: str, request: ManualFindingCreateRequest) -> str:
    """Create a reviewer-authored finding and layer."""
    layer = review_operations.add_manual_finding(
        session_id,
        label=request.label,
        reviewed_entity_type=request.reviewed_entity_type,
        description=request.description,
        reason=request.reason,
        target=review_operations.parse_target(request.target),
    )
    return layer.id


@router.patch(
    "/sessions/{session_id}/findings/{finding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_update_finding(
    session_id: str,
    finding_id: str,
    updates: FindingUpdateRequest,
) -> Response:
    """Update reviewer-editable finding fields."""
    session_store.require_session(session_id)
    patch = updates.model_dump(exclude_unset=True, mode="json")
    require_non_empty_patch(patch)
    review_operations.update_review_finding(session_id, finding_id, dict(patch))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions/{session_id}/classification-options")
async def get_classification_options(session_id: str) -> ClassificationOptionsResponse:
    """Return entity types from the session's instruction set."""
    session_store.require_session(session_id)
    return ClassificationOptionsResponse(
        options=[
            ClassificationOption.model_validate(option)
            for option in review_operations.classification_options(session_id)
        ]
    )


@router.get("/sessions/{session_id}/layers")
async def get_layers(session_id: str) -> LayersResponse:
    """Return hydrated review layers."""
    session_store.require_session(session_id)
    return LayersResponse(
        session_id=session_id,
        layers=[
            to_api_layer(layer)
            for layer in review_store.get_layers(session_id, [])
        ],
    )


@router.put(
    "/sessions/{session_id}/layers/{layer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_update_layer(
    session_id: str,
    layer_id: str,
    updates: LayerUpdateRequest,
) -> Response:
    """Update one redaction layer."""
    session_store.require_session(session_id)
    patch = updates.model_dump(exclude_unset=True)
    require_non_empty_patch(patch)
    review_operations.update_review_layer(session_id, layer_id, patch)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/sessions/{session_id}/layers/{layer_id}/effect-override",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_reset_effect_override(session_id: str, layer_id: str) -> Response:
    """Restore a layer's policy-default effect."""
    session_store.require_session(session_id)
    review_operations.reset_effect_override(session_id, layer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
