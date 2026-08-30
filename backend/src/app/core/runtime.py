"""Process-wide runtime mode used by privacy-sensitive policies."""

from __future__ import annotations

import os
from enum import StrEnum

_RUNTIME_MODE_ENV = "AIADR_RUNTIME_MODE"


class RuntimeMode(StrEnum):
    RUN = "run"
    DEV = "dev"


def configure_runtime_mode(mode: RuntimeMode) -> None:
    """Configure the runtime mode before application services are initialized."""
    os.environ[_RUNTIME_MODE_ENV] = mode.value


def runtime_mode() -> RuntimeMode:
    """Return the configured runtime mode."""
    value = os.environ.get(_RUNTIME_MODE_ENV)
    if value is None:
        raise RuntimeError("AIADR runtime mode has not been configured.")
    try:
        return RuntimeMode(value)
    except ValueError as exc:
        raise RuntimeError(f"Invalid AIADR runtime mode: {value!r}.") from exc


def sensitive_debug_enabled() -> bool:
    """Return whether raw model diagnostics may be persisted and exposed."""
    return runtime_mode() is RuntimeMode.DEV
