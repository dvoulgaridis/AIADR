"""Bounded length-prefixed JSON framing for DOCX workers."""

from __future__ import annotations

import json
import struct
from typing import IO

from app.errors import ErrorCode, app_error

MAX_FRAME_BYTES = 16 * 1024 * 1024


def write_frame(writer: IO[bytes], value: object) -> None:
    payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if not payload or len(payload) > MAX_FRAME_BYTES:
        raise app_error(ErrorCode.DOCX_PROCESSING_FAILED)
    frame = memoryview(struct.pack(">I", len(payload)) + payload)
    while frame:
        written = writer.write(frame)
        if written is None or written <= 0:
            raise OSError("DOCX processor pipe write failed.")
        frame = frame[written:]
    writer.flush()


def read_frame(reader: IO[bytes]) -> object:
    header = _read_exactly(reader, 4)
    (length,) = struct.unpack(">I", header)
    if length <= 0 or length > MAX_FRAME_BYTES:
        raise app_error(ErrorCode.DOCX_PROCESSING_FAILED)
    return json.loads(_read_exactly(reader, length))


def _read_exactly(reader: IO[bytes], length: int) -> bytes:
    result = bytearray(length)
    offset = 0
    while offset < length:
        chunk = reader.read(length - offset)
        if chunk is None:
            raise OSError("DOCX processor pipe read failed.")
        if not chunk:
            raise EOFError("DOCX processor pipe closed mid-frame.")
        result[offset : offset + len(chunk)] = chunk
        offset += len(chunk)
    return bytes(result)
