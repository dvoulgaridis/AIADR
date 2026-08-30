"""Text redaction, masking, and pseudonymization renderer."""

from __future__ import annotations

import re
from pathlib import Path

from app.domain.finding import DocumentTarget, PlainTextLocator
from app.domain.layer import Layer
from app.redaction.text_replacements import resolve_text_replacements


def _replace_in_line(line: str, exact_text: str, replacement: str) -> str:
    return line.replace(exact_text, replacement)


def render_redacted_text(
    source_path: Path,
    layers: list[Layer],
    output_path: Path,
) -> Path:
    """Render enabled text layers into an output text file."""
    lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    replacements = resolve_text_replacements(layers)
    for layer in layers:
        finding = layer.finding
        target = finding.target
        replacement = replacements.get(layer.id)
        if replacement is None or not isinstance(target, DocumentTarget):
            continue
        if not isinstance(target.locator, PlainTextLocator):
            continue
        locator = target.locator
        line_number = _line_number(locator.line_id)
        if line_number is not None and 1 <= line_number <= len(lines):
            lines[line_number - 1] = _replace_in_line(
                lines[line_number - 1],
                locator.exact_text,
                replacement,
            )
        else:
            pattern = re.escape(locator.exact_text)
            lines = [re.sub(pattern, replacement, line) for line in lines]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="utf-8")
    return output_path


def _line_number(line_id: str | None) -> int | None:
    if not line_id or not line_id.startswith("t"):
        return None
    try:
        return int(line_id[1:])
    except ValueError:
        return None
