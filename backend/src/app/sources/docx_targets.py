"""Resolve PDF-visible DOCX text back to canonical Open XML blocks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TypeVar
from unicodedata import normalize

from app.domain.finding import DocxTextLocator
from app.sources.docx_text import DocxTextBlock
from app.sources.pdf_text import PdfTextLine

_MINIMUM_MATCH_SCORE = 0.7
_MINIMUM_MATCH_MARGIN = 0.05

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class _TextProjection:
    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _PageProjection:
    text: str
    line_ids: tuple[str, ...]


def _project_text(value: str) -> _TextProjection:
    """Normalize comparison text while retaining offsets into the original value."""
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for source_index, source_character in enumerate(value):
        comparison_character = (
            "-" if source_character in {"\u00ad", "\ufffe"} else source_character
        )
        for character in normalize("NFKC", comparison_character).casefold():
            if character.isspace():
                if characters and characters[-1] != " ":
                    characters.append(" ")
                    starts.append(source_index)
                    ends.append(source_index + 1)
                elif characters:
                    ends[-1] = source_index + 1
                continue
            characters.append(character)
            starts.append(source_index)
            ends.append(source_index + 1)

    if characters and characters[-1] == " ":
        characters.pop()
        starts.pop()
        ends.pop()
    return _TextProjection("".join(characters), tuple(starts), tuple(ends))


def _compact_projection(value: str) -> _TextProjection:
    projection = _project_text(value)
    indexes = [index for index, character in enumerate(projection.text) if character != " "]
    return _TextProjection(
        "".join(projection.text[index] for index in indexes),
        tuple(projection.starts[index] for index in indexes),
        tuple(projection.ends[index] for index in indexes),
    )


def _unique_projection_span(
    source_projection: _TextProjection,
    fragment_text: str,
) -> tuple[int, int] | None:
    if not fragment_text:
        return None
    normalized_start = source_projection.text.find(fragment_text)
    if normalized_start < 0:
        return None
    if source_projection.text.find(fragment_text, normalized_start + 1) >= 0:
        return None
    normalized_end = normalized_start + len(fragment_text) - 1
    return (
        source_projection.starts[normalized_start],
        source_projection.ends[normalized_end],
    )


def _unique_source_span(source: str, fragment: str) -> tuple[int, int] | None:
    return _unique_projection_span(_project_text(source), _project_text(fragment).text)


def _unique_compact_source_span(source: str, fragment: str) -> tuple[int, int] | None:
    return _unique_projection_span(
        _compact_projection(source),
        _compact_projection(fragment).text,
    )


def _page_projection(lines: list[PdfTextLine], page: int) -> _PageProjection:
    characters: list[str] = []
    line_ids: list[str] = []
    for line in lines:
        if line.page != page:
            continue
        projection = _compact_projection(line.text)
        characters.extend(projection.text)
        line_ids.extend([line.line_id] * len(projection.text))
    return _PageProjection("".join(characters), tuple(line_ids))


def _all_starts(value: str, fragment: str) -> list[int]:
    starts: list[int] = []
    start = value.find(fragment)
    while start >= 0:
        starts.append(start)
        start = value.find(fragment, start + 1)
    return starts


def _page_selection_span(
    projection: _PageProjection,
    *,
    line_id: str,
    exact_text: str,
) -> tuple[int, int] | None:
    fragment = _compact_projection(exact_text).text
    if not fragment:
        return None
    starts = [
        start
        for start in _all_starts(projection.text, fragment)
        if start < len(projection.line_ids) and projection.line_ids[start] == line_id
    ]
    if len(starts) != 1:
        return None
    return starts[0], starts[0] + len(fragment)


def _page_context_candidates(
    blocks: list[DocxTextBlock],
    lines: list[PdfTextLine],
    *,
    page: int,
    line_id: str,
    exact_text: str,
) -> list[tuple[DocxTextBlock, tuple[int, int]]]:
    page_projection = _page_projection(lines, page)
    selection = _page_selection_span(
        page_projection,
        line_id=line_id,
        exact_text=exact_text,
    )
    if selection is None:
        return []

    selection_start, selection_end = selection
    candidates: dict[tuple[str, int, int], tuple[DocxTextBlock, tuple[int, int]]] = {}
    for block in blocks:
        block_projection = _compact_projection(block.text)
        if not block_projection.text:
            continue
        for block_start in _all_starts(page_projection.text, block_projection.text):
            block_end = block_start + len(block_projection.text)
            if not (block_start <= selection_start and selection_end <= block_end):
                continue
            relative_start = selection_start - block_start
            relative_end = selection_end - block_start - 1
            start = block_projection.starts[relative_start]
            end = block_projection.ends[relative_end]
            candidates[(block.block_id, start, end)] = (block, (start, end))
    return list(candidates.values())


def _is_wrapped_preview_selection(
    lines: list[PdfTextLine],
    *,
    page: int,
    line_id: str,
    exact_text: str,
) -> bool:
    characters: list[str] = []
    character_lines: list[str] = []
    for line in lines:
        if line.page != page:
            continue
        projection = _compact_projection(line.text)
        characters.extend(projection.text)
        character_lines.extend([line.line_id] * len(projection.text))

    fragment = _compact_projection(exact_text).text
    if not fragment:
        return False
    preview_text = "".join(characters)
    start = preview_text.find(fragment)
    if start < 0 or preview_text.find(fragment, start + 1) >= 0:
        return False
    matched_lines = character_lines[start : start + len(fragment)]
    return (
        bool(matched_lines)
        and matched_lines[0] == line_id
        and len(set(matched_lines)) > 1
    )


def _similarity(left: str, right: str) -> float:
    normalized_left = _project_text(left).text
    normalized_right = _project_text(right).text
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        coverage = min(len(normalized_left), len(normalized_right)) / max(
            len(normalized_left),
            len(normalized_right),
        )
        return 0.65 + (0.35 * coverage)
    return SequenceMatcher(
        None,
        normalized_left,
        normalized_right,
        autojunk=False,
    ).ratio()


def _preview_match_score(
    block: DocxTextBlock,
    exact_text: str,
    line: PdfTextLine,
) -> float:
    return max(
        _similarity(exact_text, line.text),
        _similarity(block.text, line.text),
    )


def _unique_best_match(
    candidates: list[_T],
    score: Callable[[_T], float],
) -> _T | None:
    ranked = sorted(
        ((score(candidate), candidate) for candidate in candidates),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < _MINIMUM_MATCH_SCORE:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < _MINIMUM_MATCH_MARGIN:
        return None
    return ranked[0][1]


def _preview_line_for_block(
    block: DocxTextBlock,
    exact_text: str,
    lines: list[PdfTextLine],
) -> PdfTextLine | None:
    return _unique_best_match(
        lines,
        lambda line: _preview_match_score(block, exact_text, line),
    )


def locator_for_block(
    block: DocxTextBlock,
    exact_text: str,
    lines: list[PdfTextLine],
    *,
    source_sha256: str,
) -> DocxTextLocator | None:
    """Build a locator only when both Open XML and PDF evidence are unambiguous."""
    span = _unique_source_span(block.text, exact_text)
    if span is None:
        return None
    line = _preview_line_for_block(block, exact_text, lines)
    if line is None:
        return None
    start, end = span
    canonical_text = block.text[start:end]
    return DocxTextLocator(
        page=line.page,
        line_id=line.line_id,
        source_sha256=source_sha256,
        story_kind=block.story_kind,
        part_uri=block.part_uri,
        block_id=block.block_id,
        start=start,
        end=end,
        exact_text=canonical_text,
    )


def is_valid_locator(
    block: DocxTextBlock,
    locator: DocxTextLocator,
    lines: list[PdfTextLine],
    *,
    source_sha256: str,
) -> bool:
    """Verify a stored locator against canonical DOCX and PDF evidence."""
    if (
        locator.source_sha256 != source_sha256
        or locator.story_kind != block.story_kind
        or locator.part_uri != block.part_uri
        or locator.block_id != block.block_id
        or locator.end > len(block.text)
        or block.text[locator.start : locator.end] != locator.exact_text
    ):
        return False

    context_candidates = _page_context_candidates(
        [block],
        lines,
        page=locator.page,
        line_id=locator.line_id,
        exact_text=locator.exact_text,
    )
    if any(span == (locator.start, locator.end) for _, span in context_candidates):
        return True
    return locator_for_block(
        block,
        locator.exact_text,
        lines,
        source_sha256=source_sha256,
    ) == locator


def resolve_pdf_selection(
    blocks: list[DocxTextBlock],
    lines: list[PdfTextLine],
    *,
    page: int,
    line_id: str,
    exact_text: str,
    source_sha256: str,
) -> DocxTextLocator | None:
    """Resolve one same-page PDF selection to exactly one Open XML source range."""
    line = next(
        (item for item in lines if item.page == page and item.line_id == line_id),
        None,
    )
    if line is None:
        return None

    candidates = _page_context_candidates(
        blocks,
        lines,
        page=page,
        line_id=line_id,
        exact_text=exact_text,
    )
    if not candidates:
        wrapped = _unique_source_span(line.text, exact_text) is None
        if wrapped and not _is_wrapped_preview_selection(
            lines,
            page=page,
            line_id=line_id,
            exact_text=exact_text,
        ):
            return None
        span_for = _unique_compact_source_span if wrapped else _unique_source_span
        candidates = [
            (block, span)
            for block in blocks
            if (span := span_for(block.text, exact_text)) is not None
        ]
    match = candidates[0] if len(candidates) == 1 else _unique_best_match(
        candidates,
        lambda candidate: _preview_match_score(candidate[0], exact_text, line),
    )
    if match is None:
        return None
    block, (start, end) = match
    canonical_text = block.text[start:end]
    return DocxTextLocator(
        page=page,
        line_id=line_id,
        source_sha256=source_sha256,
        story_kind=block.story_kind,
        part_uri=block.part_uri,
        block_id=block.block_id,
        start=start,
        end=end,
        exact_text=canonical_text,
    )
