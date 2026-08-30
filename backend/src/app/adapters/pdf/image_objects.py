"""Read raster image objects and normalized placement geometry from PDFs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image

_SIGNATURE_SIZE = (32, 32)


@dataclass(frozen=True, slots=True)
class PdfImageObject:
    page: int
    object_index: int
    width_px: int
    height_px: int
    signature: bytes
    x: float
    y: float
    width: float
    height: float
    rotation_degrees: float


def image_signature(image: Image.Image) -> bytes:
    """Return a small deterministic RGB signature suitable for decoded-pixel comparison."""
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    background.alpha_composite(rgba)
    rgb = background.convert("RGB")
    resized = rgb.resize(_SIGNATURE_SIZE, Image.Resampling.LANCZOS)
    try:
        return resized.tobytes()
    finally:
        resized.close()
        rgb.close()
        background.close()
        rgba.close()


def signature_distance(left: bytes, right: bytes) -> float:
    """Return mean absolute channel distance for equal-sized RGB signatures."""
    if len(left) != len(right) or not left:
        raise ValueError("PDF image signatures must have the same non-zero length")
    return sum(abs(a - b) for a, b in zip(left, right, strict=True)) / len(left)


def read_image_objects(path: Path) -> tuple[PdfImageObject, ...]:
    """Enumerate concrete PDF image objects in stable page/object order."""
    document = pdfium.PdfDocument(path)
    result: list[PdfImageObject] = []
    try:
        for page_index in range(len(document)):
            page = document.get_page(page_index)
            try:
                page_width, page_height = page.get_size()
                images = page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE])
                for object_index, image_object in enumerate(images):
                    width_px, height_px = image_object.get_px_size()
                    if width_px <= 0 or height_px <= 0:
                        continue
                    bitmap = image_object.get_bitmap(render=False, scale_to_original=True)
                    try:
                        pixels = bitmap.to_pil().copy()
                    finally:
                        bitmap.close()
                    try:
                        geometry = _placement(
                            image_object.get_quad_points(),
                            page_width,
                            page_height,
                        )
                        result.append(
                            PdfImageObject(
                                page=page_index + 1,
                                object_index=object_index,
                                width_px=width_px,
                                height_px=height_px,
                                signature=image_signature(pixels),
                                **geometry,
                            )
                        )
                    finally:
                        pixels.close()
            finally:
                page.close()
    finally:
        document.close()
    return tuple(result)


def _placement(
    quad: tuple[tuple[float, float], ...],
    page_width: float,
    page_height: float,
) -> dict[str, float]:
    if len(quad) != 4 or page_width <= 0 or page_height <= 0:
        raise ValueError("PDF image placement is invalid")
    bottom_left, _, top_right, top_left = quad
    width = math.dist(top_left, top_right)
    height = math.dist(top_left, bottom_left)
    if width <= 0 or height <= 0:
        raise ValueError("PDF image placement is empty")
    center_x = sum(point[0] for point in quad) / 4
    center_y = sum(point[1] for point in quad) / 4
    normalized_width = width / page_width
    normalized_height = height / page_height
    x = center_x / page_width - normalized_width / 2
    y = (page_height - center_y) / page_height - normalized_height / 2
    return {
        "x": _bounded(x, 0, 1 - normalized_width),
        "y": _bounded(y, 0, 1 - normalized_height),
        "width": min(normalized_width, 1),
        "height": min(normalized_height, 1),
        "rotation_degrees": _normalize_degrees(
            -math.degrees(
                math.atan2(top_right[1] - top_left[1], top_right[0] - top_left[0])
            )
        ),
    }


def _bounded(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_degrees(value: float) -> float:
    return (value + 180) % 360 - 180
