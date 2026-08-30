"""JSON extraction helpers for provider responses.

This module contains only generic parsing behavior. It knows nothing about
AIADR findings, policy defaults, review decisions, or redaction layers.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any


class JsonObjectExtractionError(ValueError):
    """Raised when text does not contain a parseable JSON object."""


def _top_level_object_starts(text: str) -> Iterator[int]:
    """Yield object starts without mistaking nested objects for responses."""
    stack: list[str] = []
    in_string = False
    escaped = False
    matching = {"}": "{", "]": "["}

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"' and stack:
            in_string = True
            continue
        if not stack:
            if char == "{":
                stack.append(char)
                yield index
            continue
        if char in "{[":
            stack.append(char)
        elif char in "}]":
            if stack[-1] != matching[char]:
                stack.clear()
            else:
                stack.pop()


def _repair_incomplete_object(candidate: str) -> str | None:
    """Recover one missing item close or the root object's final close."""
    stack: list[str] = []
    repaired: list[str] = []
    in_string = False
    escaped = False
    matching = {"}": "{", "]": "["}
    inserted_item_close = False

    for char in candidate:
        if in_string:
            repaired.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            repaired.append(char)
        elif char in "{[":
            stack.append(char)
            repaired.append(char)
        elif char in "}]":
            if (
                char == "]"
                and stack
                and stack[-1] == "{"
                and not inserted_item_close
            ):
                repaired.append("}")
                stack.pop()
                inserted_item_close = True
            if not stack or stack[-1] != matching[char]:
                return None
            stack.pop()
            repaired.append(char)
        else:
            repaired.append(char)

    if in_string:
        return None
    if stack == ["{"]:
        repaired.append("}")
        stack.pop()
    if stack or (not inserted_item_close and len(repaired) == len(candidate)):
        return None
    return "".join(repaired)


def extract_json_object(raw: str) -> dict[str, Any]:
    """Return the first JSON object embedded in provider response text."""
    text = raw.strip()
    if not text:
        raise JsonObjectExtractionError("Model returned an empty response.")
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    decoder = json.JSONDecoder()
    for index in _top_level_object_starts(text):
        candidate = text[index:]
        try:
            value, _end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            completed = _repair_incomplete_object(candidate)
            if completed is None:
                continue
            try:
                value, _end = decoder.raw_decode(completed)
            except json.JSONDecodeError:
                continue
        if isinstance(value, dict):
            return value
    raise JsonObjectExtractionError(
        "Model returned output that could not be parsed as a JSON object.",
    )
