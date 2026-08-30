"""Persist the model and instruction set selected for future analysis."""

from __future__ import annotations

from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ValidationError

from app.core.paths import data_root
from app.errors import ErrorCode, app_error


class _ActiveSelection(BaseModel):
    model_id: str | None = None
    instruction_set_id: str | None = None

    model_config = {"extra": "forbid", "frozen": True}


_LOCK = RLock()


def _path() -> Path:
    directory = data_root() / "settings"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "active.json"


def _load() -> _ActiveSelection:
    path = _path()
    if not path.is_file():
        return _ActiveSelection()
    try:
        return _ActiveSelection.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, OSError) as exc:
        raise app_error(
            ErrorCode.SETTINGS_STORE_INVALID,
            details={"path": str(path), "reason": type(exc).__name__},
        ) from exc


def _save(selection: _ActiveSelection) -> None:
    path = _path()
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(selection.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise app_error(
            ErrorCode.SETTINGS_STORE_INVALID,
            details={"path": str(path), "reason": type(exc).__name__},
        ) from exc


def active_model_id() -> str | None:
    with _LOCK:
        return _load().model_id


def active_instruction_set_id() -> str | None:
    with _LOCK:
        return _load().instruction_set_id


def set_active_model_id(model_id: str | None) -> None:
    with _LOCK:
        _save(_load().model_copy(update={"model_id": model_id}))


def set_active_instruction_set_id(instruction_set_id: str | None) -> None:
    with _LOCK:
        _save(_load().model_copy(update={"instruction_set_id": instruction_set_id}))
