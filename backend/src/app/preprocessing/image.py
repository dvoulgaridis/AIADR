"""Build bounded image inputs for model detection."""

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

IMAGE_ANALYSIS_MAX_EDGE = 1600
IMAGE_ANALYSIS_JPEG_QUALITY = 85


@dataclass(frozen=True, slots=True)
class ImageAnalysisInput:
    """A model-ready image plus dimensions of its original source."""

    path: Path
    mime_type: str
    display_width: int
    display_height: int


def inspect_image(file_path: Path) -> tuple[int, int]:
    """Return display dimensions after applying EXIF orientation."""
    with Image.open(file_path) as opened_image:
        return ImageOps.exif_transpose(opened_image).size


def write_analysis_jpeg(image: Image.Image, output_path: Path) -> None:
    """Normalize and write one bounded JPEG model input."""
    image.thumbnail(
        (IMAGE_ANALYSIS_MAX_EDGE, IMAGE_ANALYSIS_MAX_EDGE),
        Image.Resampling.LANCZOS,
    )
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        output_path,
        format="JPEG",
        quality=IMAGE_ANALYSIS_JPEG_QUALITY,
        optimize=True,
    )


def build_image_input(file_path: Path, output_path: Path) -> ImageAnalysisInput:
    """Read an image once and write its bounded model input."""
    with Image.open(file_path) as opened_image:
        analysis_image = ImageOps.exif_transpose(opened_image)
        display_width, display_height = analysis_image.size
        write_analysis_jpeg(analysis_image, output_path)
    return ImageAnalysisInput(
        path=output_path,
        mime_type="image/jpeg",
        display_width=display_width,
        display_height=display_height,
    )
