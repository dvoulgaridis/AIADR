"""Load the canonical checked-in OpenAPI document for FastAPI documentation."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, cast

import yaml
from fastapi import FastAPI

from app.core.paths import project_root


@lru_cache
def load_openapi_contract() -> dict[str, Any]:
    """Parse and cache the canonical API contract."""
    path = project_root() / "contracts" / "openapi.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("The canonical OpenAPI contract must be a mapping.")
    return cast(dict[str, Any], document)


def install_openapi_contract(app: FastAPI) -> None:
    """Make FastAPI docs serve the canonical contract rather than deriving one."""
    contract = load_openapi_contract()

    def canonical_openapi() -> dict[str, Any]:
        return contract

    app.openapi_schema = contract
    app.openapi = canonical_openapi  # type: ignore[method-assign]
