"""Inspect audio sources with user-installed FFmpeg tools."""

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from app.core.config import FFMPEG_PATH
from app.errors import ErrorCode, app_error

FFMPEG_TIMEOUT_SECONDS = 30


class FFmpegStatus(BaseModel):
    """Runtime FFmpeg availability status."""

    available: bool
    path: str | None = None
    version: str | None = None
    error: str | None = None


def ffmpeg_binary() -> str | None:
    """Return the configured or PATH FFmpeg binary."""
    if FFMPEG_PATH:
        return FFMPEG_PATH
    return shutil.which("ffmpeg")


def ffprobe_binary() -> str | None:
    """Return the companion ffprobe binary when available."""
    if FFMPEG_PATH:
        candidate = Path(FFMPEG_PATH).with_name("ffprobe")
        if candidate.exists():
            return str(candidate)
    return shutil.which("ffprobe")


def ffmpeg_status() -> FFmpegStatus:
    """Check whether the required FFmpeg command-line tools are available."""
    binary = ffmpeg_binary()
    if not binary:
        return FFmpegStatus(available=False, error="FFmpeg not found on PATH.")
    detected_path = str(Path(binary).expanduser().resolve())
    if not ffprobe_binary():
        return FFmpegStatus(
            available=False,
            path=detected_path,
            error="ffprobe was not found alongside FFmpeg or on PATH.",
        )
    try:
        proc = subprocess.run(
            [binary, "-version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return FFmpegStatus(
            available=False,
            path=detected_path,
            error="FFmpeg availability check timed out.",
        )
    except OSError:
        return FFmpegStatus(
            available=False,
            path=detected_path,
            error="FFmpeg could not be executed.",
        )
    first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
    return FFmpegStatus(
        available=proc.returncode == 0,
        path=detected_path,
        version=first_line,
        error=None if proc.returncode == 0 else f"FFmpeg exited with status {proc.returncode}.",
    )


def _audio_metadata(file_path: Path) -> tuple[float, int]:
    probe = ffprobe_binary()
    if not probe:
        raise app_error(
            ErrorCode.FFMPEG_UNAVAILABLE,
            details={"reason": "ffprobe_not_found"},
        )
    try:
        proc = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate:format=duration",
                "-of",
                "json",
                str(file_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except OSError as exc:
        raise app_error(
            ErrorCode.FFMPEG_UNAVAILABLE,
            details={"reason": "ffprobe_execution_failed"},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise app_error(
            ErrorCode.UNSUPPORTED_UPLOAD_TYPE,
            details={"reason": "audio_probe_timed_out"},
        ) from exc
    if proc.returncode != 0:
        raise app_error(
            ErrorCode.UNSUPPORTED_UPLOAD_TYPE,
            details={"reason": "invalid_audio_file"},
        )
    try:
        data = json.loads(proc.stdout)
        duration = float(data["format"]["duration"])
        streams = data.get("streams", [])
        sample_rate = int(streams[0]["sample_rate"]) if streams else None
        if duration <= 0 or sample_rate is None or sample_rate <= 0:
            raise ValueError
        return duration, sample_rate
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise app_error(
            ErrorCode.UNSUPPORTED_UPLOAD_TYPE,
            details={"reason": "audio_metadata_missing"},
        ) from None


@dataclass(frozen=True, slots=True)
class AudioInfo:
    """Metadata inspected from an audio source."""

    duration_seconds: float
    sample_rate: int


def inspect_audio(file_path: Path) -> AudioInfo:
    """Validate an audio source and return its required metadata."""
    if not ffmpeg_binary() or not ffprobe_binary():
        raise app_error(
            ErrorCode.FFMPEG_UNAVAILABLE,
            details={"reason": "ffmpeg_or_ffprobe_not_found"},
        )
    duration_seconds, sample_rate = _audio_metadata(file_path)
    return AudioInfo(duration_seconds=duration_seconds, sample_rate=sample_rate)
