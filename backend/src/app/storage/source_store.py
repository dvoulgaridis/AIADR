"""Persist structured indexes derived from submitted sources.

This boundary currently owns PDF text lines and may own future text or audio
indexes. Uploaded files, session metadata, findings, prompts, and provider data
remain in their dedicated stores.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from app.sources.docx_images import DocxImageOccurrence
from app.sources.docx_text import DocxTextBlock
from app.sources.pdf_text import PdfTextLine
from app.storage import db


def replace_pdf_lines_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    lines: Sequence[PdfTextLine],
) -> None:
    """Replace all PDF text evidence using the caller's transaction."""
    connection.execute(
        "DELETE FROM pdf_text_lines WHERE session_id = ?",
        (session_id,),
    )
    connection.executemany(
        """
        INSERT INTO pdf_text_lines (session_id, page, line_id, text)
        VALUES (?, ?, ?, ?)
        """,
        [(session_id, line.page, line.line_id, line.text) for line in lines],
    )


def get_pdf_lines(session_id: str) -> list[PdfTextLine]:
    """Return all page-aware text lines in display order."""
    rows = db.fetchall(
        """
        SELECT page, line_id, text
        FROM pdf_text_lines
        WHERE session_id = ?
        ORDER BY page ASC, line_id ASC
        """,
        (session_id,),
    )
    return [PdfTextLine.model_validate(dict(row)) for row in rows]


def replace_docx_blocks_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    blocks: Sequence[DocxTextBlock],
) -> None:
    """Replace one session's canonical DOCX text evidence."""
    connection.execute("DELETE FROM docx_text_blocks WHERE session_id = ?", (session_id,))
    connection.executemany(
        """
        INSERT INTO docx_text_blocks (
            session_id, block_id, ordinal, story_kind, part_uri, structural_path, text
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                session_id,
                block.block_id,
                block.ordinal,
                block.story_kind,
                block.part_uri,
                block.structural_path,
                block.text,
            )
            for block in blocks
        ],
    )


def get_docx_blocks(session_id: str) -> list[DocxTextBlock]:
    """Return canonical DOCX blocks in source order."""
    rows = db.fetchall(
        """
        SELECT block_id, ordinal, story_kind, part_uri, structural_path, text
        FROM docx_text_blocks
        WHERE session_id = ?
        ORDER BY ordinal ASC
        """,
        (session_id,),
    )
    return [DocxTextBlock.model_validate(dict(row)) for row in rows]


def replace_docx_image_occurrences_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
    occurrences: Sequence[DocxImageOccurrence],
) -> None:
    """Replace one session's complete DOCX picture inventory."""
    connection.execute(
        "DELETE FROM docx_image_occurrences WHERE session_id = ?",
        (session_id,),
    )
    connection.executemany(
        """
        INSERT INTO docx_image_occurrences (
            session_id, occurrence_id, ordinal, story_kind, part_uri,
            media_type, asset_filename, normalized_sha256,
            width_px, height_px, targetable, unsupported_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                session_id,
                occurrence.occurrence_id,
                occurrence.ordinal,
                occurrence.story_kind,
                occurrence.part_uri,
                occurrence.media_type,
                occurrence.asset_filename,
                occurrence.normalized_sha256,
                occurrence.width_px,
                occurrence.height_px,
                int(occurrence.targetable),
                occurrence.unsupported_reason,
            )
            for occurrence in occurrences
        ],
    )


def get_docx_image_occurrences(session_id: str) -> list[DocxImageOccurrence]:
    """Return DOCX picture occurrences in stable source order."""
    rows = db.fetchall(
        """
        SELECT occurrence_id, ordinal, story_kind, part_uri, media_type,
               asset_filename, normalized_sha256,
               width_px, height_px, targetable, unsupported_reason
        FROM docx_image_occurrences
        WHERE session_id = ?
        ORDER BY ordinal ASC
        """,
        (session_id,),
    )
    return [
        DocxImageOccurrence.model_validate({**dict(row), "targetable": bool(row["targetable"])})
        for row in rows
    ]
