"""Review aggregate projections for the HTTP boundary."""

from app.api.contracts import Layer as ApiLayer
from app.domain.layer import Layer


def to_api_layer(layer: Layer) -> ApiLayer:
    """Validate and return a generated hydrated-layer response."""
    return ApiLayer.model_validate(layer.model_dump(mode="json"))
