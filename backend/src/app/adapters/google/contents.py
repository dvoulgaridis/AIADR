"""Google Gen AI content construction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import cast

from app.errors import JsonValue
from app.inference.requests import DetectionRequest

from google.genai import types


@dataclass(frozen=True, slots=True)
class GoogleRequestBody:
    system_instruction: str
    contents: list[types.Content]


def build_contents(request: DetectionRequest) -> tuple[GoogleRequestBody, dict[str, JsonValue]]:
    source_json = json.dumps(
        request.source_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    parts = [types.Part.from_text(text=source_json)]
    log_parts: list[dict[str, JsonValue]] = [{"type": "text", "text": source_json}]
    if request.attachment is not None:
        attachment = request.attachment
        parts.append(types.Part.from_bytes(data=attachment.data, mime_type=attachment.mime_type))
        log_parts.append(
            {
                "type": "inline_data",
                "mime_type": attachment.mime_type,
                "omitted_from_log": True,
                "byte_length": len(attachment.data),
                "sha256": hashlib.sha256(attachment.data).hexdigest(),
            }
        )
    body = GoogleRequestBody(
        system_instruction=request.system_prompt,
        contents=[types.Content(role="user", parts=parts)],
    )
    return body, cast(
        dict[str, JsonValue],
        {
            "system_instruction": request.system_prompt,
            "contents": [{"role": "user", "parts": log_parts}],
        },
    )
