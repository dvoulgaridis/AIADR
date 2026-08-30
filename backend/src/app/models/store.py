"""Persistent model store.

Models are local application state. They are stored in
``data/settings/models.json`` and converted to provider settings by
``app.models.settings``.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.core.ids import new_model_id
from app.core.paths import data_root
from app.errors import ErrorCode, app_error
from app.models.model import Model
from app.models.settings import model_is_configured
from app.settings.selection import (
    active_model_id,
    set_active_model_id,
)


class _ModelsFile(BaseModel):
    """Private JSON persistence envelope."""

    models: list[Model] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


def _store_path() -> Path:
    path = data_root() / "settings"
    path.mkdir(parents=True, exist_ok=True)
    return path / "models.json"


def _load_models() -> dict[str, Model]:
    path = _store_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            stored = _ModelsFile.model_validate(data)
            models = {
                model.model_id: model.model_copy(
                    update={"configured": model_is_configured(model)},
                )
                for model in stored.models
                if model.model_id
            }
            return models
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            raise app_error(
                ErrorCode.MODEL_STORE_INVALID,
                details={"path": str(path), "reason": type(exc).__name__},
            ) from exc

    return {}


def _persist_models() -> None:
    models = _ensure_loaded()
    stored = _ModelsFile(
        models=list(models.values()),
    )
    _store_path().write_text(stored.model_dump_json(indent=2), encoding="utf-8")


_models: dict[str, Model] | None = None


def _ensure_loaded() -> dict[str, Model]:
    global _models
    if _models is None:
        _models = _load_models()
    return _models


def get_active_model_id() -> str | None:
    """Return the selected model ID without resolving the model."""
    return active_model_id()


def get_active_model() -> Model:
    """Return the model selected for future analysis."""
    models = _ensure_loaded()
    if not models:
        raise app_error(ErrorCode.NO_MODELS)
    model_id = active_model_id()
    if model_id is None:
        raise app_error(ErrorCode.ACTIVE_MODEL_NOT_SET)
    return get_model(model_id)


def list_models() -> list[Model]:
    """Return all saved models."""
    return list(_ensure_loaded().values())


def save_model(model: Model) -> Model:
    """Create or update a saved model."""
    models = _ensure_loaded()
    model_id = model.model_id or new_model_id()
    saved = model.model_copy(
        update={
            "model_id": model_id,
            "configured": model_is_configured(model),
        },
    )
    models[model_id] = saved
    _persist_models()
    return saved


def activate_model(model_id: str) -> None:
    """Select one saved model for future analysis."""
    get_model(model_id)
    set_active_model_id(model_id)


def get_model(model_id: str) -> Model:
    """Return a saved model by ID."""
    try:
        return _ensure_loaded()[model_id]
    except KeyError as exc:
        raise app_error(
            ErrorCode.MODEL_NOT_FOUND,
            details={"model_id": model_id},
        ) from exc


def find_model(model_id: str) -> Model | None:
    """Return a saved model by ID when it exists."""
    return _ensure_loaded().get(model_id)


def delete_model(model_id: str) -> None:
    """Delete a saved model."""
    models = _ensure_loaded()
    if model_id not in models:
        raise app_error(
            ErrorCode.MODEL_NOT_FOUND,
            details={"model_id": model_id},
        )
    del models[model_id]
    _persist_models()
    if active_model_id() == model_id:
        set_active_model_id(None)
