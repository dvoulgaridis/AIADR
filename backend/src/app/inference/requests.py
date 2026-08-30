"""Provider-neutral inputs for one model detection request."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.errors import JsonValue
from app.sources.kinds import SourceKind


class ModelRequestSummary(BaseModel):
    """Content-free measurements of one provider-neutral request."""

    source_payload_bytes: int = Field(ge=0)
    line_count: int | None = Field(default=None, ge=0)
    character_count: int | None = Field(default=None, ge=0)
    attachment_kind: SourceKind | None = None
    attachment_mime_type: str | None = None
    attachment_size_bytes: int | None = Field(default=None, ge=0)
    attachment_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    system_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = {"extra": "forbid", "frozen": True}


@dataclass(frozen=True, slots=True)
class BinaryAttachment:
    """One source attachment supplied to a multimodal model request."""

    kind: SourceKind
    mime_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class DetectionRequest:
    """The smallest source evidence contract shared by provider adapters."""

    system_prompt: str
    source_payload: Mapping[str, JsonValue]
    attachment: BinaryAttachment | None = None


def _source_json(request: DetectionRequest) -> str:
    return json.dumps(
        request.source_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def summarize_request(request: DetectionRequest) -> ModelRequestSummary:
    """Return content-free request measurements for durable diagnostics."""
    source = request.source_payload.get("source")
    lines = source.get("lines") if isinstance(source, Mapping) else None
    line_count = len(lines) if isinstance(lines, list) else None
    character_count: int | None = None
    if isinstance(lines, list):
        texts: list[str] = []
        for line in lines:
            if not isinstance(line, Mapping):
                break
            text = line.get("text")
            if not isinstance(text, str):
                break
            texts.append(text)
        else:
            character_count = sum(len(text) for text in texts)

    attachment = request.attachment
    return ModelRequestSummary(
        source_payload_bytes=len(_source_json(request).encode("utf-8")),
        line_count=line_count,
        character_count=character_count,
        attachment_kind=attachment.kind if attachment else None,
        attachment_mime_type=attachment.mime_type if attachment else None,
        attachment_size_bytes=len(attachment.data) if attachment else None,
        attachment_sha256=(
            hashlib.sha256(attachment.data).hexdigest() if attachment else None
        ),
        system_prompt_sha256=hashlib.sha256(request.system_prompt.encode("utf-8")).hexdigest(),
    )
