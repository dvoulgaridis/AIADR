"""Raster PDF output assembled from redacted page images."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from app.domain.finding import PdfPageSurface
from app.domain.layer import Layer
from app.redaction.image_renderer import apply_image_effects, image_layers_for_surface
from PIL import Image
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]

PDF_EXPORT_DPI = 200


def _flatten(image: Image.Image) -> Image.Image:
    """Return an opaque RGB page suitable for deterministic PDF embedding."""
    rgba = image.convert("RGBA")
    flattened = Image.new("RGB", rgba.size, "white")
    flattened.paste(rgba, mask=rgba.getchannel("A"))
    rgba.close()
    return flattened


def render_raster_pdf(
    source_path: Path,
    layers: list[Layer],
    destination: Path,
) -> Path:
    """Render every PDF page, apply page-local effects, and assemble one PDF."""
    source = pdfium.PdfDocument(str(source_path))
    try:
        if len(source) < 1:
            raise ValueError("PDF contains no pages")
        destination.parent.mkdir(parents=True, exist_ok=True)
        output = Canvas(
            str(destination),
            pagesize=(1, 1),
            pageCompression=1,
            invariant=1,
        )
        output.setAuthor("AIADR")
        output.setCreator("AIADR")
        output.setSubject("Rendered review output")
        output.setTitle("AIADR rendered output")

        for page_index in range(len(source)):
            page = source[page_index]
            try:
                width_points, height_points = page.get_size()
                bitmap = page.render(scale=PDF_EXPORT_DPI / 72)
                try:
                    page_image = bitmap.to_pil()
                finally:
                    bitmap.close()
                try:
                    page_number = page_index + 1
                    rendered = apply_image_effects(
                        page_image,
                        image_layers_for_surface(
                            layers,
                            PdfPageSurface(page=page_number),
                        ),
                    )
                finally:
                    page_image.close()
                try:
                    flattened = _flatten(rendered)
                finally:
                    rendered.close()
                try:
                    encoded = BytesIO()
                    flattened.save(encoded, format="JPEG", quality=92, optimize=True)
                    encoded.seek(0)
                    output.setPageSize((width_points, height_points))
                    output.drawImage(
                        ImageReader(encoded),
                        0,
                        0,
                        width=width_points,
                        height=height_points,
                        preserveAspectRatio=False,
                    )
                    output.showPage()
                finally:
                    flattened.close()
            finally:
                page.close()

        output.save()
        return destination
    finally:
        source.close()
