"""Small .env loader for local runtime overrides."""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def _clean_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env without overriding process environment."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True

    env_path = path or Path.cwd() / ".env"
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = _clean_value(value)
