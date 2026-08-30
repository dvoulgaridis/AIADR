"""Repository-root and runtime data path utilities.

All backend code that needs local files should resolve paths through this
module. It deliberately fails loudly if the repository root cannot be found.
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import DATA_DIR


def project_root() -> Path:
    """Return the AIADR repository root."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "backend").is_dir():
            return parent
    raise RuntimeError("Could not locate AIADR project root.")


def instruction_sets_root() -> Path:
    """Return the root instruction-set asset directory."""
    return project_root() / "instruction_sets"


def data_root() -> Path:
    """Return the root data directory path."""
    path = Path(DATA_DIR)
    return path if path.is_absolute() else project_root() / path


def db_path() -> Path:
    """Return the SQLite database path."""
    return data_root() / "aiadr.db"


def uploads_dir(session_id: str) -> Path:
    """Return the upload directory for a session."""
    path = data_root() / "uploads" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def outputs_dir(session_id: str) -> Path:
    """Return the output directory for a session."""
    path = data_root() / "outputs" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def previews_dir(session_id: str) -> Path:
    """Return the derived preview-cache directory for a session."""
    path = data_root() / "previews" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepared_dir(session_id: str) -> Path:
    """Return the private derived-source directory for a session."""
    path = data_root() / "prepared" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def exports_dir(session_id: str) -> Path:
    """Return the export directory for a session."""
    path = data_root() / "exports" / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_data_dirs() -> None:
    """Ensure top-level data directories exist."""
    for subdir in ("uploads", "outputs", "exports", "prepared", "previews"):
        (data_root() / subdir).mkdir(parents=True, exist_ok=True)
