"""Prepare bounded WAV attachments for OpenAI-compatible audio inference."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.errors import ErrorCode, app_error
from app.sources.audio import FFMPEG_TIMEOUT_SECONDS, ffmpeg_binary, inspect_audio

INFERENCE_SAMPLE_RATE = 16_000
AUDIO_CHUNK_SECONDS = 300.0
AUDIO_CHUNK_OVERLAP_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class AudioInput:
    """One canonical attachment and its position in the source timeline."""

    path: Path
    start_time: float
    duration_seconds: float
    source_duration_seconds: float


def _chunk_starts(duration_seconds: float) -> list[float]:
    step = AUDIO_CHUNK_SECONDS - AUDIO_CHUNK_OVERLAP_SECONDS
    starts = [0.0]
    while starts[-1] + AUDIO_CHUNK_SECONDS < duration_seconds:
        starts.append(starts[-1] + step)
    return starts


def build_audio_inputs(source_path: Path, destination_dir: Path) -> tuple[AudioInput, ...]:
    """Create mono PCM WAV chunks without altering the uploaded source."""
    binary = ffmpeg_binary()
    if not binary:
        raise app_error(ErrorCode.FFMPEG_UNAVAILABLE)

    info = inspect_audio(source_path)
    destination_dir.mkdir(parents=True, exist_ok=True)
    for stale_chunk in destination_dir.glob("chunk-*.wav"):
        stale_chunk.unlink()

    inputs: list[AudioInput] = []
    for index, start in enumerate(_chunk_starts(info.duration_seconds), start=1):
        duration = min(AUDIO_CHUNK_SECONDS, info.duration_seconds - start)
        destination = destination_dir / f"chunk-{index:04d}.wav"
        temporary = destination.with_name(f".{destination.stem}.tmp{destination.suffix}")
        temporary.unlink(missing_ok=True)
        try:
            try:
                process = subprocess.run(
                    [
                        binary,
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        f"{start:.6f}",
                        "-i",
                        str(source_path),
                        "-t",
                        f"{duration:.6f}",
                        "-map",
                        "0:a:0",
                        "-vn",
                        "-sn",
                        "-dn",
                        "-map_metadata",
                        "-1",
                        "-ac",
                        "1",
                        "-ar",
                        str(INFERENCE_SAMPLE_RATE),
                        "-c:a",
                        "pcm_s16le",
                        str(temporary),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=max(FFMPEG_TIMEOUT_SECONDS, int(duration * 2) + 30),
                )
            except OSError as exc:
                raise app_error(
                    ErrorCode.FFMPEG_UNAVAILABLE,
                    details={"reason": "ffmpeg_execution_failed"},
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise app_error(
                    ErrorCode.AUDIO_RENDER_FAILED,
                    details={
                        "reason": "inference_input_timed_out",
                        "chunk": index,
                    },
                ) from exc
            if process.returncode != 0 or not temporary.is_file():
                raise app_error(
                    ErrorCode.AUDIO_RENDER_FAILED,
                    details={
                        "exit_code": process.returncode,
                        "stage": "inference_input",
                        "chunk": index,
                    },
                )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        inputs.append(
            AudioInput(
                path=destination,
                start_time=start,
                duration_seconds=duration,
                source_duration_seconds=info.duration_seconds,
            )
        )
    return tuple(inputs)
