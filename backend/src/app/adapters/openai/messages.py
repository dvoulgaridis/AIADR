"""OpenAI-compatible Chat Completions request construction."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.errors import JsonValue
from app.inference.requests import DetectionRequest
from app.sources.kinds import SourceKind


@dataclass(frozen=True, slots=True)
class OpenAIRequestBody:
    messages: list[dict[str, Any]]
    log_messages: list[dict[str, JsonValue]]
    text_byte_count: int


def _source_json(request: DetectionRequest) -> str:
    return json.dumps(
        request.source_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def build_messages(request: DetectionRequest) -> OpenAIRequestBody:
    """Build native messages and an attachment-safe diagnostic projection."""
    source_json = _source_json(request)
    system_message: dict[str, Any] = {"role": "system", "content": request.system_prompt}
    text_bytes = len(request.system_prompt.encode()) + len(source_json.encode())
    if request.attachment is None:
        messages = [system_message, {"role": "user", "content": source_json}]
        return OpenAIRequestBody(
            messages=messages,
            log_messages=messages,
            text_byte_count=text_bytes,
        )

    attachment = request.attachment
    digest = hashlib.sha256(attachment.data).hexdigest()
    if attachment.kind is SourceKind.IMAGE:
        encoded = base64.b64encode(attachment.data).decode("ascii")
        provider_part: dict[str, Any] = {
            "type": "image_url",
            "image_url": {"url": f"data:{attachment.mime_type};base64,{encoded}"},
        }
        log_part: dict[str, JsonValue] = {
            "type": "image_url",
            "image_url": {
                "url": f"data:{attachment.mime_type};base64,<omitted>",
                "omitted_from_log": True,
                "byte_length": len(attachment.data),
                "sha256": digest,
            },
        }
    elif attachment.kind is SourceKind.AUDIO:
        encoded = base64.b64encode(attachment.data).decode("ascii")
        provider_part = {
            "type": "input_audio",
            "input_audio": {"data": encoded, "format": "wav"},
        }
        log_part = {
            "type": "input_audio",
            "input_audio": {
                "data": "<omitted>",
                "format": "wav",
                "omitted_from_log": True,
                "byte_length": len(attachment.data),
                "sha256": digest,
            },
        }
    else:
        raise ValueError(f"Unsupported OpenAI attachment kind: {attachment.kind}")

    provider_user: dict[str, Any] = {
        "role": "user",
        "content": [{"type": "text", "text": source_json}, provider_part],
    }
    log_user: dict[str, JsonValue] = {
        "role": "user",
        "content": [{"type": "text", "text": source_json}, log_part],
    }
    return OpenAIRequestBody(
        messages=[system_message, provider_user],
        log_messages=[system_message, log_user],
        text_byte_count=text_bytes,
    )
