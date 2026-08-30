"""Map durable DOCX picture occurrences to derived PDF preview placements."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from app.adapters.pdf.image_objects import (
    PdfImageObject,
    image_signature,
    read_image_objects,
    signature_distance,
)
from app.domain.finding import DocxPictureSurface, TargetRegion
from app.domain.layer import Layer
from app.redaction.image_renderer import apply_image_effects, image_layers_for_surface
from app.sources.docx_images import DocxImageOccurrence, DocxPicturePlacement
from app.storage.file_store import require_docx_image_asset

_MAX_SIGNATURE_DISTANCE = 12.0


@dataclass(frozen=True, slots=True)
class _ExpectedPicture:
    occurrence: DocxImageOccurrence
    signature: bytes
    aspect_ratio: float


def project_docx_picture_placements(
    session_id: str,
    pdf_path: Path,
    occurrences: tuple[DocxImageOccurrence, ...],
    layers: list[Layer],
) -> tuple[DocxPicturePlacement, ...]:
    """Associate every targetable occurrence with one concrete PDF image object."""
    expected = tuple(
        _expected_picture(session_id, occurrence, layers)
        for occurrence in sorted(occurrences, key=lambda item: item.ordinal)
        if occurrence.targetable
    )
    if not expected:
        return ()

    candidates = read_image_objects(pdf_path)
    scored = sorted(
        (
            signature_distance(picture.signature, candidate.signature),
            _aspect_ratio_distance(picture.aspect_ratio, candidate),
            picture.occurrence.ordinal,
            candidate.page,
            candidate.object_index,
            picture,
            candidate,
        )
        for picture in expected
        for candidate in candidates
    )
    assigned_occurrences: set[str] = set()
    assigned_candidates: set[tuple[int, int]] = set()
    placements: list[DocxPicturePlacement] = []
    for score, _, _, _, _, picture, candidate in scored:
        occurrence_id = picture.occurrence.occurrence_id
        candidate_id = (candidate.page, candidate.object_index)
        if (
            score > _MAX_SIGNATURE_DISTANCE
            or occurrence_id in assigned_occurrences
            or candidate_id in assigned_candidates
        ):
            continue
        assigned_occurrences.add(occurrence_id)
        assigned_candidates.add(candidate_id)
        placements.append(
            DocxPicturePlacement(
                occurrence_id=occurrence_id,
                page=candidate.page,
                region=TargetRegion(
                    x=candidate.x,
                    y=candidate.y,
                    width=candidate.width,
                    height=candidate.height,
                    rotation_degrees=candidate.rotation_degrees,
                ),
            )
        )

    expected_ids = {picture.occurrence.occurrence_id for picture in expected}
    if assigned_occurrences != expected_ids:
        raise ValueError("DOCX picture placements could not be resolved from the PDF preview")
    ordinals = {
        picture.occurrence.occurrence_id: picture.occurrence.ordinal for picture in expected
    }
    return tuple(
        sorted(
            placements,
            key=lambda item: ordinals[item.occurrence_id],
        )
    )


def _expected_picture(
    session_id: str,
    occurrence: DocxImageOccurrence,
    layers: list[Layer],
) -> _ExpectedPicture:
    if (
        occurrence.asset_filename is None
        or occurrence.normalized_sha256 is None
        or occurrence.width_px is None
        or occurrence.height_px is None
    ):
        raise ValueError("A targetable DOCX picture is missing normalized evidence")
    path = require_docx_image_asset(
        session_id,
        occurrence.asset_filename,
        occurrence.normalized_sha256,
    )
    surface = DocxPictureSurface(occurrence_id=occurrence.occurrence_id)
    with Image.open(path) as source:
        rendered = apply_image_effects(source, image_layers_for_surface(layers, surface))
    try:
        return _ExpectedPicture(
            occurrence=occurrence,
            signature=image_signature(rendered),
            aspect_ratio=occurrence.width_px / occurrence.height_px,
        )
    finally:
        rendered.close()


def _aspect_ratio_distance(
    expected: float,
    candidate: PdfImageObject,
) -> float:
    actual = candidate.width_px / candidate.height_px
    return abs(expected - actual) / expected
