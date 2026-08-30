"""Authoritative FFmpeg renderer for audio preview and export."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from app.domain.finding import AudioTarget, ReviewDecision
from app.domain.layer import Layer, LayerAction, LayerEffect
from app.errors import ErrorCode, app_error
from app.sources.audio import FFMPEG_TIMEOUT_SECONDS, ffmpeg_binary, inspect_audio

BLEEP_FREQUENCY_HZ = 1_000
BLEEP_GAIN = 0.35
BLEEP_FADE_SECONDS = 0.008
RENDER_SAMPLE_RATE = 48_000

_EFFECT_PRIORITY: dict[LayerEffect, int] = {
    LayerEffect.BLEEP: 1,
    LayerEffect.MUTE: 2,
}
_OUTPUT_CODECS: dict[str, tuple[str, ...]] = {
    ".aac": ("-c:a", "aac"),
    ".flac": ("-c:a", "flac"),
    ".m4a": ("-c:a", "aac"),
    ".mp3": ("-c:a", "libmp3lame"),
    ".mp4": ("-c:a", "aac"),
    ".ogg": ("-c:a", "libopus"),
    ".opus": ("-c:a", "libopus"),
    ".wav": ("-c:a", "pcm_s16le"),
    ".webm": ("-c:a", "libopus"),
}


@dataclass(frozen=True, slots=True)
class _EffectSpan:
    start: float
    end: float
    effect: LayerEffect


def supported_output_suffix(source_suffix: str) -> str:
    """Return a renderable output suffix, defaulting unknown containers to WAV."""
    normalized = source_suffix.lower()
    return normalized if normalized in _OUTPUT_CODECS else ".wav"


def _active_spans(layers: list[Layer], duration: float) -> list[_EffectSpan]:
    candidates: list[_EffectSpan] = []
    for layer in layers:
        target = layer.finding.target
        if (
            not layer.enabled
            or layer.action is LayerAction.PRESERVE
            or layer.finding.review_decision is not ReviewDecision.CONFIRMED
            or not isinstance(target, AudioTarget)
            or layer.effect not in _EFFECT_PRIORITY
        ):
            continue
        start = max(0.0, min(target.range.start_time, duration))
        end = max(0.0, min(target.range.end_time, duration))
        if end > start:
            candidates.append(
                _EffectSpan(start=start, end=end, effect=layer.effect),
            )
    if not candidates:
        return []

    boundaries = sorted({point for span in candidates for point in (span.start, span.end)})
    resolved: list[_EffectSpan] = []
    for start, end in pairwise(boundaries):
        effects = [
            span.effect
            for span in candidates
            if span.start < end and span.end > start
        ]
        if not effects:
            continue
        effect = max(effects, key=_EFFECT_PRIORITY.__getitem__)
        if resolved and resolved[-1].effect == effect and resolved[-1].end == start:
            previous = resolved[-1]
            resolved[-1] = _EffectSpan(
                start=previous.start,
                end=end,
                effect=effect,
            )
        else:
            resolved.append(_EffectSpan(start=start, end=end, effect=effect))
    return resolved


def _filter_graph(spans: list[_EffectSpan]) -> tuple[str, list[str]]:
    muted = ",".join(
        (
            "volume=volume=0:"
            f"enable='between(t,{span.start:.6f},{span.end:.6f})'"
        )
        for span in spans
    )
    base_filters = [
        (
            f"aformat=sample_fmts=fltp:sample_rates={RENDER_SAMPLE_RATE}:"
            "channel_layouts=stereo"
        )
    ]
    if muted:
        base_filters.append(muted)

    filter_parts = [f"[0:a:0]{','.join(base_filters)}[base]"]
    command_inputs: list[str] = []
    bleep_labels: list[str] = []
    bleep_index = 0
    for span in spans:
        if span.effect is not LayerEffect.BLEEP:
            continue
        duration = span.end - span.start
        fade = min(BLEEP_FADE_SECONDS, duration / 2)
        delay_ms = round(span.start * 1_000)
        command_inputs.extend(
            [
                "-f",
                "lavfi",
                "-i",
                (
                    f"sine=frequency={BLEEP_FREQUENCY_HZ}:"
                    f"sample_rate={RENDER_SAMPLE_RATE}:duration={duration:.6f}"
                ),
            ]
        )
        label = f"bleep{bleep_index}"
        filter_parts.append(
            f"[{bleep_index + 1}:a]"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"afade=t=in:st=0:d={fade:.6f},"
            f"afade=t=out:st={duration - fade:.6f}:d={fade:.6f},"
            f"volume={BLEEP_GAIN},adelay={delay_ms}:all=1[{label}]"
        )
        bleep_labels.append(f"[{label}]")
        bleep_index += 1

    if bleep_labels:
        filter_parts.append(
            f"[base]{''.join(bleep_labels)}"
            f"amix=inputs={len(bleep_labels) + 1}:duration=first:"
            "dropout_transition=0:normalize=0[aout]"
        )
    else:
        filter_parts.append("[base]anull[aout]")
    return ";".join(filter_parts), command_inputs


def render_redacted_audio(
    source_path: Path,
    layers: list[Layer],
    output_path: Path,
) -> Path:
    """Render current confirmed audio effects into an explicit output container."""
    binary = ffmpeg_binary()
    if not binary:
        raise app_error(ErrorCode.FFMPEG_UNAVAILABLE)

    info = inspect_audio(source_path)
    spans = _active_spans(layers, info.duration_seconds)
    filters, generated_inputs = _filter_graph(spans)
    suffix = supported_output_suffix(output_path.suffix)
    if suffix != output_path.suffix.lower():
        raise ValueError(f"Unsupported audio output suffix: {output_path.suffix}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}.tmp{output_path.suffix}")
    temporary.unlink(missing_ok=True)
    try:
        try:
            process = subprocess.run(
                [
                    binary,
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(source_path),
                    *generated_inputs,
                    "-filter_complex",
                    filters,
                    "-map",
                    "[aout]",
                    "-vn",
                    "-sn",
                    "-dn",
                    "-map_metadata",
                    "-1",
                    *_OUTPUT_CODECS[suffix],
                    str(temporary),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=max(FFMPEG_TIMEOUT_SECONDS, int(info.duration_seconds * 2) + 30),
            )
        except OSError as exc:
            raise app_error(
                ErrorCode.FFMPEG_UNAVAILABLE,
                details={"reason": "ffmpeg_execution_failed"},
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise app_error(
                ErrorCode.AUDIO_RENDER_FAILED,
                details={"reason": "audio_render_timed_out"},
            ) from exc
        if process.returncode != 0 or not temporary.is_file():
            raise app_error(
                ErrorCode.AUDIO_RENDER_FAILED,
                details={"exit_code": process.returncode},
            )
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path
