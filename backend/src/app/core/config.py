"""Environment-derived application configuration.

This module exposes scalar settings only. Filesystem path resolution lives in
``app.core.paths``.
"""

from __future__ import annotations

import os

from app.core.env import load_dotenv

load_dotenv()


def _boolean_setting(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise RuntimeError(f"{name} must be 'true' or 'false'.")


DATA_DIR = os.getenv("AIADR_DATA_DIR", "data")
LOG_LEVEL = os.getenv("AIADR_LOG_LEVEL", "INFO")
ALLOW_LAN = _boolean_setting("AIADR_ALLOW_LAN", default=False)
HOST = "0.0.0.0" if ALLOW_LAN else "127.0.0.1"
PORT = int(os.getenv("AIADR_SERVER_PORT", "7860"))
MAX_UPLOAD_MB = int(os.getenv("AIADR_MAX_UPLOAD_MB", "50"))
FFMPEG_PATH = os.getenv("AIADR_FFMPEG_PATH", "")
LIBREOFFICE_PATH = os.getenv("AIADR_LIBREOFFICE_PATH", "")
EXPORT_HMAC_SECRET = os.getenv("AIADR_EXPORT_HMAC_SECRET", "")
DOCX_WORKERS = int(os.getenv("AIADR_DOCX_WORKERS", "2"))
if DOCX_WORKERS < 1:
    raise RuntimeError("AIADR_DOCX_WORKERS must be at least 1.")
