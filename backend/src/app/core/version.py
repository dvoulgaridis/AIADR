"""Expose the AIADR development version and source identity."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from functools import lru_cache

from app.core.paths import project_root

_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Identify the exact source checkout when that information is available."""

    revision: str | None
    modified: bool | None


@lru_cache(maxsize=1)
def application_version() -> str:
    """Return the root ``pyproject.toml`` project version."""
    document = tomllib.loads((project_root() / "pyproject.toml").read_text(encoding="utf-8"))
    project = document.get("project")
    if not isinstance(project, dict):
        raise RuntimeError("pyproject.toml does not define [project].")
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("pyproject.toml does not define a valid project version.")
    return version


def _validate_revision(value: str) -> str:
    revision = value.strip().lower()
    if _REVISION_PATTERN.fullmatch(revision) is None:
        raise RuntimeError("AIADR source revision must be a full Git commit hash.")
    return revision


@lru_cache(maxsize=1)
def source_identity() -> SourceIdentity:
    """Return the Git revision and dirty state without treating either as a version."""
    configured_revision = os.getenv("AIADR_SOURCE_REVISION")
    if configured_revision is not None:
        return SourceIdentity(
            revision=_validate_revision(configured_revision),
            modified=None,
        )

    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=project_root(),
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return SourceIdentity(revision=None, modified=None)

    return SourceIdentity(
        revision=_validate_revision(revision),
        modified=bool(status.strip()),
    )
