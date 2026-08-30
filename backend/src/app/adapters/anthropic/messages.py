"""Anthropic Messages request construction."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast

from app.errors import JsonValue
from app.inference.requests import DetectionRequest
from app.sources.kinds import SourceKind


@dataclass(frozen=True, slots=True)
class AnthropicRequestBody:
    system: str
    messages: list[dict[str, Any]]


def build_messages(request: DetectionRequest) -> tuple[AnthropicRequestBody, dict[str, JsonValue]]:
    source_json = json.dumps(
        request.source_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    content: list[dict[str, Any]] = [{"type": "text", "text": source_json}]
    log_content: list[dict[str, JsonValue]] = [{"type": "text", "text": source_json}]
    if request.attachment is not None:
        attachment = request.attachment
        if attachment.kind is not SourceKind.IMAGE:
            raise ValueError("Anthropic Messages supports image attachments only in AIADR")
        encoded = base64.b64encode(attachment.data).decode("ascii")
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": attachment.mime_type,
                    "data": encoded,
                },
            }
        )
        log_content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": attachment.mime_type,
                    "data": "<omitted>",
                    "omitted_from_log": True,
                    "byte_length": len(attachment.data),
                    "sha256": hashlib.sha256(attachment.data).hexdigest(),
                },
            }
        )
    body = AnthropicRequestBody(
        system=request.system_prompt,
        messages=[{"role": "user", "content": content}],
    )
    return body, cast(
        dict[str, JsonValue],
        {
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": log_content}],
        },
    )
