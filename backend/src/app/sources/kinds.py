"""Canonical source-kind vocabulary."""

from enum import StrEnum


class SourceKind(StrEnum):
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
