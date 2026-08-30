"""Validation not represented reliably by generated boundary models."""

from app.errors import ErrorCode, app_error


def require_non_empty_patch(patch: dict[str, object]) -> None:
    """Reject structurally valid update requests that contain no fields."""
    if patch:
        return
    raise app_error(ErrorCode.EMPTY_UPDATE)
