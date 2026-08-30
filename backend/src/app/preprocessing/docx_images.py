"""Normalize visible DOCX picture occurrences into deterministic PNG evidence."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps, UnidentifiedImageError

from app.adapters.docx.contracts import ProcessorImageOccurrence
from app.core.paths import prepared_dir
from app.sources.docx_images import DocxImageOccurrence


def normalize_docx_images(
    session_id: str,
    raw_directory: Path,
    projected: Sequence[ProcessorImageOccurrence],
) -> tuple[DocxImageOccurrence, ...]:
    """Publish one normalized visible bitmap for every decodable occurrence."""
    prepared = prepared_dir(session_id)
    target_directory = prepared / "docx-images"
    with TemporaryDirectory(prefix=".docx-images-", dir=prepared) as temporary:
        staging = Path(temporary)
        occurrences = tuple(
            _normalize_occurrence(item, raw_directory, staging) for item in projected
        )
        if target_directory.exists():
            shutil.rmtree(target_directory)
        staging.replace(target_directory)
    return occurrences


def _normalize_occurrence(
    item: ProcessorImageOccurrence,
    raw_directory: Path,
    output_directory: Path,
) -> DocxImageOccurrence:
    if not item.targetable or item.source_asset is None:
        return _unsupported(item, item.unsupported_reason or "unsupported_picture")

    source = _controlled_asset(raw_directory, item.source_asset)
    try:
        with Image.open(source) as opened:
            opened.seek(0)
            visible = ImageOps.exif_transpose(opened)
            cropped = _crop_visible_bitmap(visible, item)
            if item.flip_horizontal:
                cropped = ImageOps.mirror(cropped)
            if item.flip_vertical:
                cropped = ImageOps.flip(cropped)
            normalized = cropped.convert("RGBA")
    except (OSError, UnidentifiedImageError, ValueError):
        return _unsupported(item, "unsupported_or_invalid_bitmap")

    filename = f"{item.id}.png"
    destination = output_directory / filename
    try:
        normalized.save(destination, format="PNG", compress_level=9, optimize=False)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return DocxImageOccurrence(
            occurrence_id=item.id,
            ordinal=item.ordinal,
            story_kind=item.story_kind,
            part_uri=item.part_uri,
            media_type="image/png",
            asset_filename=filename,
            normalized_sha256=digest,
            width_px=normalized.width,
            height_px=normalized.height,
            targetable=True,
            unsupported_reason=None,
        )
    finally:
        normalized.close()


def _crop_visible_bitmap(
    image: Image.Image,
    item: ProcessorImageOccurrence,
) -> Image.Image:
    horizontal = item.crop_left + item.crop_right
    vertical = item.crop_top + item.crop_bottom
    if horizontal >= 100000 or vertical >= 100000:
        raise ValueError("DOCX picture crop removes the complete bitmap")
    left = round(image.width * item.crop_left / 100000)
    top = round(image.height * item.crop_top / 100000)
    right = image.width - round(image.width * item.crop_right / 100000)
    bottom = image.height - round(image.height * item.crop_bottom / 100000)
    if right <= left or bottom <= top:
        raise ValueError("DOCX picture crop is empty")
    return image.crop((left, top, right, bottom))


def _controlled_asset(directory: Path, filename: str) -> Path:
    root = directory.resolve()
    path = (root / filename).resolve()
    if path.parent != root or not path.is_file():
        raise ValueError("DOCX processor returned an invalid image asset path")
    return path


def _unsupported(item: ProcessorImageOccurrence, reason: str) -> DocxImageOccurrence:
    return DocxImageOccurrence(
        occurrence_id=item.id,
        ordinal=item.ordinal,
        story_kind=item.story_kind,
        part_uri=item.part_uri,
        media_type=item.media_type,
        targetable=False,
        unsupported_reason=reason,
    )
