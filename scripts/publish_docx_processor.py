"""Publish self-contained DOCX processor artifacts for one or more runtimes."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT / "docx-processor"
PROJECT = PROJECT_ROOT / "Aiadr.Docx.csproj"

TARGET_FRAMEWORK = "net10.0"
CONFIGURATION = "Release"
SUPPORTED_RIDS = (
    "linux-x64",
    "linux-arm64",
    "win-x64",
    "win-arm64",
    "osx-x64",
    "osx-arm64",
)


def _current_rid() -> str:
    systems = {
        "Linux": "linux",
        "Windows": "win",
        "Darwin": "osx",
    }
    machines = {
        "x86_64": "x64",
        "AMD64": "x64",
        "aarch64": "arm64",
        "ARM64": "arm64",
        "arm64": "arm64",
    }

    try:
        return f"{systems[platform.system()]}-{machines[platform.machine()]}"
    except KeyError as exc:
        raise RuntimeError("The current platform has no supported DOCX runtime ID.") from exc


def _publish_directory(rid: str) -> Path:
    return PROJECT_ROOT / "bin" / CONFIGURATION / TARGET_FRAMEWORK / rid / "publish"


def _restore(dotnet: str) -> None:
    subprocess.run(
        [
            dotnet,
            "restore",
            str(PROJECT),
            "--locked-mode",
        ],
        cwd=ROOT,
        check=True,
    )


def _publish(dotnet: str, rid: str) -> Path:
    output = _publish_directory(rid)
    shutil.rmtree(output, ignore_errors=True)

    subprocess.run(
        [
            dotnet,
            "publish",
            str(PROJECT),
            "--configuration",
            CONFIGURATION,
            "--framework",
            TARGET_FRAMEWORK,
            "--runtime",
            rid,
            "--self-contained",
            "true",
            "--no-restore",
            "-p:DebugType=None",
        ],
        cwd=ROOT,
        check=True,
    )

    executable_name = "aiadr-docx.exe" if rid.startswith("win-") else "aiadr-docx"
    executable = output / executable_name
    if not executable.is_file():
        raise RuntimeError(f"DOCX processor executable was not created: {executable}")

    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rid",
        action="append",
        dest="rids",
        choices=SUPPORTED_RIDS,
        help=".NET runtime ID to publish",
    )
    args = parser.parse_args()

    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise RuntimeError("The .NET 10 SDK is required to publish the DOCX processor.")

    rids = args.rids or [_current_rid()]
    _restore(dotnet)

    for rid in rids:
        output = _publish(dotnet, rid)
        print(f"Published DOCX processor for {rid}: {output}")


if __name__ == "__main__":
    main()
