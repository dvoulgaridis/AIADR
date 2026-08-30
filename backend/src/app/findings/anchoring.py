"""Connect extracted findings to source media anchors.

Anchoring is the step after extraction and before policy enrichment. It aligns
candidate findings with stable source references such as PDF page text lines.
"""

from __future__ import annotations

from app.domain.finding import (
    AudioRange,
    AudioTarget,
    DocumentTarget,
    Finding,
    ImageSurface,
    ImageTarget,
    PlainTextLocator,
)
from app.preprocessing.text import TextLine
from app.sources.docx_targets import locator_for_block
from app.sources.docx_text import DocxTextBlock
from app.sources.pdf_text import PdfTextLine


def anchor_image_findings(
    findings: list[Finding],
    surface: ImageSurface,
) -> list[Finding]:
    """Bind valid model image regions to an application-owned source surface."""
    anchored: list[Finding] = []
    for finding in findings:
        if not isinstance(finding.target, ImageTarget):
            continue
        anchored.append(
            finding.model_copy(
                update={
                    "target": ImageTarget(
                        surface=surface,
                        region=finding.target.region,
                    )
                }
            )
        )
    return anchored


def anchor_text_findings(
    findings: list[Finding],
    text_lines: tuple[TextLine, ...],
) -> list[Finding]:
    """Keep text findings that resolve to their submitted source line."""
    lines_by_id = {line.line_id: line.text for line in text_lines}
    return [
        finding
        for finding in findings
        if isinstance(finding.target, DocumentTarget)
        and isinstance(finding.target.locator, PlainTextLocator)
        and finding.target.locator.exact_text
        in lines_by_id.get(finding.target.locator.line_id, "")
    ]


def anchor_docx_findings(
    findings: list[Finding],
    blocks: tuple[DocxTextBlock, ...],
    *,
    source_sha256: str,
    preview_lines: list[PdfTextLine],
) -> list[Finding]:
    """Resolve line-like model findings to unambiguous DOCX source ranges."""
    blocks_by_id = {block.block_id: block for block in blocks}
    anchored: list[Finding] = []
    for finding in findings:
        target = finding.target
        if not isinstance(target, DocumentTarget) or not isinstance(
            target.locator,
            PlainTextLocator,
        ):
            continue
        locator = target.locator
        block = blocks_by_id.get(locator.line_id)
        if block is None:
            continue
        resolved = locator_for_block(
            block,
            locator.exact_text,
            preview_lines,
            source_sha256=source_sha256,
        )
        if resolved is None:
            continue
        anchored.append(
            finding.model_copy(
                update={
                    "target": DocumentTarget(
                        locator=resolved,
                    )
                }
            )
        )
    return anchored


def anchor_audio_findings(
    findings: list[Finding],
    *,
    attachment_start_seconds: float,
    attachment_duration_seconds: float,
    source_duration_seconds: float,
) -> list[Finding]:
    """Translate attachment-relative model ranges onto the source timeline."""
    anchored: list[Finding] = []
    for finding in findings:
        target = finding.target
        if not isinstance(target, AudioTarget):
            continue
        relative_start = target.range.start_time
        relative_end = min(
            target.range.end_time,
            attachment_duration_seconds,
        )
        if relative_start >= attachment_duration_seconds or relative_end <= relative_start:
            continue
        start = min(
            attachment_start_seconds + relative_start,
            source_duration_seconds,
        )
        end = min(
            attachment_start_seconds + relative_end,
            source_duration_seconds,
        )
        if end <= start:
            continue
        anchored.append(
            finding.model_copy(
                update={
                    "target": AudioTarget(
                        range=AudioRange(start_time=start, end_time=end),
                    )
                }
            )
        )
    return anchored


def deduplicate_audio_findings(findings: list[Finding]) -> list[Finding]:
    """Merge matching findings repeated by overlapping inference chunks."""
    deduplicated: list[Finding] = []
    for finding in sorted(
        findings,
        key=lambda item: (
            item.target.range.start_time if isinstance(item.target, AudioTarget) else 0.0
        ),
    ):
        target = finding.target
        if not isinstance(target, AudioTarget):
            continue
        duplicate_index = next(
            (
                index
                for index, candidate in enumerate(deduplicated)
                if isinstance(candidate.target, AudioTarget)
                and candidate.detected_entity_type == finding.detected_entity_type
                and candidate.label.casefold() == finding.label.casefold()
                and candidate.target.range.end_time >= target.range.start_time
            ),
            None,
        )
        if duplicate_index is None:
            deduplicated.append(finding)
            continue
        existing = deduplicated[duplicate_index]
        assert isinstance(existing.target, AudioTarget)
        finding_confidence = (
            finding.detection_confidence
            if finding.detection_confidence is not None
            else -1.0
        )
        existing_confidence = (
            existing.detection_confidence
            if existing.detection_confidence is not None
            else -1.0
        )
        preferred = finding if finding_confidence > existing_confidence else existing
        deduplicated[duplicate_index] = preferred.model_copy(
            update={
                "target": AudioTarget(
                    range=AudioRange(
                        start_time=min(
                            existing.target.range.start_time,
                            target.range.start_time,
                        ),
                        end_time=max(
                            existing.target.range.end_time,
                            target.range.end_time,
                        ),
                    )
                )
            }
        )
    return deduplicated
