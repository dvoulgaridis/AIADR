"""Generate backend and frontend bindings from the OpenAPI contract."""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPENAPI_CONTRACT = PROJECT_ROOT / "contracts" / "openapi.yaml"


def _validate_contract_version() -> None:
    project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]
    contract = yaml.safe_load(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
    if contract["info"]["version"] != project["version"]:
        raise RuntimeError("OpenAPI info.version must match the AIADR project version.")


def _required_command(name: str) -> str:
    command = shutil.which(name)
    if command is None:
        raise RuntimeError(f"Required command is not available on PATH: {name}")
    return command


def generate_contracts() -> None:
    """Generate both committed API contract bindings."""
    _validate_contract_version()
    datamodel_codegen = _required_command("datamodel-codegen")
    pnpm = _required_command("pnpm")

    subprocess.run(
        [
            datamodel_codegen,
            "--input",
            str(OPENAPI_CONTRACT),
            "--input-file-type",
            "openapi",
            "--output",
            str(PROJECT_ROOT / "backend" / "src" / "app" / "api" / "generated" / "contracts.py"),
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--use-standard-collections",
            "--use-union-operator",
            "--use-annotated",
            "--disable-timestamp",
            "--formatters",
            "ruff-check",
            "ruff-format",
            "--target-python-version",
            "3.11",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )
    subprocess.run(
        [
            pnpm,
            "--dir",
            "frontend",
            "exec",
            "openapi-typescript",
            "../contracts/openapi.yaml",
            "--output",
            "src/api/generated/openapi.ts",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )


if __name__ == "__main__":
    generate_contracts()
