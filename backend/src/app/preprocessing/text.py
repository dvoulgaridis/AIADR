"""Build complete, line-indexed text inputs for model detection."""

from dataclasses import dataclass
from pathlib import Path

from app.errors import ErrorCode, app_error


@dataclass(frozen=True, slots=True)
class TextLine:
    """One stable line in a text model input."""

    line_id: str
    text: str


@dataclass(frozen=True, slots=True)
class TextInput:
    """One line-aligned model input from a complete text source."""

    content: str
    lines: tuple[TextLine, ...]


def build_text_inputs(
    file_path: Path,
    *,
    request_byte_limit: int | None,
) -> tuple[TextInput, ...]:
    """Return line-aligned inputs that cover the complete source exactly once."""
    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = tuple(
        TextLine(line_id=f"t{index + 1}", text=line)
        for index, line in enumerate(content.splitlines())
        if line.strip()
    )
    if not lines:
        return (TextInput(content=content, lines=()),)
    if request_byte_limit is None:
        return (TextInput(content=content, lines=lines),)

    inputs: list[TextInput] = []
    batch: list[TextLine] = []
    batch_size = 0
    for line in lines:
        line_size = len(line.text.encode()) + 1
        if line_size > request_byte_limit:
            raise app_error(
                ErrorCode.TEXT_LINE_TOO_LARGE,
                details={
                    "line_id": line.line_id,
                    "line_bytes": len(line.text.encode()),
                    "request_byte_limit": request_byte_limit,
                },
            )
        if batch and batch_size + line_size > request_byte_limit:
            batch_lines = tuple(batch)
            inputs.append(
                TextInput(
                    content="\n".join(item.text for item in batch_lines),
                    lines=batch_lines,
                )
            )
            batch = []
            batch_size = 0
        batch.append(line)
        batch_size += line_size

    batch_lines = tuple(batch)
    inputs.append(
        TextInput(
            content="\n".join(item.text for item in batch_lines),
            lines=batch_lines,
        )
    )
    return tuple(inputs)
