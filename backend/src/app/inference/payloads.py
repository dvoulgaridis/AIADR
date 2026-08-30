"""Serialize provider-neutral source evidence for inference."""

from collections.abc import Iterable

from app.errors import JsonValue
from app.preprocessing.text import TextLine
from app.sources.docx_text import DocxTextBlock


def text_source_payload(lines: Iterable[TextLine]) -> dict[str, JsonValue]:
    return {
        "source": {
            "kind": "text",
            "lines": [{"line_id": line.line_id, "text": line.text} for line in lines],
        }
    }


def docx_source_payload(blocks: Iterable[DocxTextBlock]) -> dict[str, JsonValue]:
    """Serialize canonical DOCX blocks as line-like model evidence."""
    return {
        "source": {
            "kind": "document",
            "format": "docx",
            "lines": [{"line_id": block.block_id, "text": block.text} for block in blocks],
        }
    }


def image_source_payload() -> dict[str, JsonValue]:
    return {"source": {"kind": "image"}}


def audio_source_payload(
    *,
    start_time: float,
    duration_seconds: float,
) -> dict[str, JsonValue]:
    return {
        "source": {
            "kind": "audio",
            "timestamp_basis": "attachment_relative",
            "attachment_start_seconds": start_time,
            "duration_seconds": duration_seconds,
        }
    }
