"""Image redaction renderer."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.domain.finding import ImageSurface, ImageTarget, ReviewDecision
from app.domain.layer import Layer, LayerAction, LayerEffect


def _pixel_box(target: ImageTarget, width: int, height: int) -> tuple[int, int, int, int] | None:
    region = target.region
    x1 = max(0, min(width, round(region.x * width)))
    y1 = max(0, min(height, round(region.y * height)))
    x2 = max(0, min(width, round((region.x + region.width) * width)))
    y2 = max(0, min(height, round((region.y + region.height) * height)))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def _target_mask(
    size: tuple[int, int],
    box: tuple[int, int, int, int],
    rotation_degrees: float,
) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rectangle(box, fill=255)
    if abs(rotation_degrees) < 0.01:
        return mask
    x1, y1, x2, y2 = box
    center = ((x1 + x2) / 2, (y1 + y2) / 2)
    return mask.rotate(
        -rotation_degrees,
        resample=Image.Resampling.BICUBIC,
        center=center,
        fillcolor=0,
    )


def _pixelated(image: Image.Image, box: tuple[int, int, int, int] | None = None) -> Image.Image:
    if box is None:
        small = image.resize((max(1, image.width // 12), max(1, image.height // 12)))
        return small.resize(image.size, Image.Resampling.NEAREST)
    region = image.crop(box)
    small = region.resize((max(1, region.width // 12), max(1, region.height // 12)))
    return small.resize(region.size, Image.Resampling.NEAREST)


def image_layers_for_surface(
    layers: Sequence[Layer],
    surface: ImageSurface,
) -> tuple[Layer, ...]:
    """Return renderable image layers for one coordinate surface in stable order."""
    return tuple(
        sorted(
            (
                layer
                for layer in layers
                if layer.enabled
                and layer.action is not LayerAction.PRESERVE
                and layer.finding.review_decision is ReviewDecision.CONFIRMED
                and isinstance(layer.finding.target, ImageTarget)
                and layer.finding.target.surface == surface
            ),
            key=lambda layer: layer.id,
        )
    )


def apply_image_effects(image: Image.Image, layers: Sequence[Layer]) -> Image.Image:
    """Return a copy with the supplied image layers applied in stable order."""
    image = image.convert("RGBA").copy()
    width, height = image.size

    for layer in sorted(layers, key=lambda item: item.id):
        if (
            not layer.enabled
            or layer.action is LayerAction.PRESERVE
            or layer.finding.review_decision is not ReviewDecision.CONFIRMED
        ):
            continue
        target = layer.finding.target
        if not isinstance(target, ImageTarget):
            continue
        box = _pixel_box(target, width, height)
        if box is None:
            continue
        rotation = target.region.rotation_degrees
        if abs(rotation) >= 0.01:
            mask = _target_mask(image.size, box, rotation)
            if layer.effect is LayerEffect.BLUR:
                image.paste(image.filter(ImageFilter.GaussianBlur(radius=12)), mask=mask)
            elif layer.effect is LayerEffect.PIXELATE:
                image.paste(_pixelated(image), mask=mask)
            else:
                fill = Image.new("RGBA", image.size, layer.fill_color or "#000000")
                image.paste(fill, mask=mask)
            continue
        if layer.effect is LayerEffect.BLUR:
            region = image.crop(box).filter(ImageFilter.GaussianBlur(radius=12))
            image.paste(region, box)
        elif layer.effect is LayerEffect.PIXELATE:
            image.paste(_pixelated(image, box), box)
        else:
            ImageDraw.Draw(image).rectangle(box, fill=layer.fill_color or "#000000")

    return image


def render_redacted_image(
    source_path: Path,
    layers: Sequence[Layer],
    output_path: Path,
) -> Path:
    """Render visual layers onto an image without mutating the source."""
    with Image.open(source_path) as source:
        image = apply_image_effects(source, layers)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, format="PNG")
    image.close()
    return output_path
