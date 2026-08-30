"""Extract candidate findings from provider response text.

Extraction converts provider output into local Finding objects. It deliberately
does not apply policy defaults; analysis orchestration owns that later step.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.core.ids import new_finding_id
from app.domain.finding import (
    AudioRange,
    AudioTarget,
    DocumentTarget,
    FileImageSurface,
    Finding,
    FindingOrigin,
    FindingTarget,
    ImageTarget,
    PlainTextLocator,
    TargetRegion,
)
from app.parsers.json import JsonObjectExtractionError, extract_json_object

logger = logging.getLogger(__name__)


class ExtractionKind(StrEnum):
    """Provider-output shape used to construct finding targets."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


class FindingExtractionError(ValueError):
    """Raised when provider output cannot be converted into findings."""


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Valid findings and the number of malformed entries rejected."""

    findings: tuple[Finding, ...]
    rejected_count: int


def _clamp_unit(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _target_region(raw_region: object) -> TargetRegion | None:
    if not isinstance(raw_region, dict):
        return None
    x = _clamp_unit(raw_region.get("x"))
    y = _clamp_unit(raw_region.get("y"))
    width = min(_clamp_unit(raw_region.get("width"), default=0.1), 1.0 - x)
    height = min(_clamp_unit(raw_region.get("height"), default=0.1), 1.0 - y)
    if width <= 0.0 or height <= 0.0:
        return None
    return TargetRegion(x=x, y=y, width=width, height=height)


def _validate_model_owned_fields(item: dict[str, Any]) -> None:
    forbidden = {
        "privacy_category",
        "special_category_type",
        "privacy_risk",
        "action",
        "effect",
    }
    present = sorted(forbidden.intersection(item))
    if present:
        raise FindingExtractionError(
            f"Model finding contains policy-owned field(s): {', '.join(present)}."
        )


def _finding_target(
    item: dict[str, Any],
    kind: ExtractionKind,
) -> FindingTarget:
    if kind == ExtractionKind.IMAGE:
        region = _target_region(item.get("target_region"))
        if region is None:
            raise ValueError("image finding requires target_region")
        return ImageTarget(surface=FileImageSurface(), region=region)
    if kind == ExtractionKind.TEXT:
        return DocumentTarget(
            locator=PlainTextLocator(
                line_id=str(item.get("line_id") or ""),
                exact_text=str(item.get("exact_text") or ""),
            ),
        )
    raw_range = item.get("audio_range")
    if not isinstance(raw_range, dict):
        raise ValueError("audio finding requires audio_range")
    return AudioTarget(range=AudioRange.model_validate(raw_range))


def extract_findings(
    raw: str,
    kind: ExtractionKind,
    created_by: str,
    page: int | None = None,
) -> ExtractionResult:
    """Extract candidate findings from raw provider JSON output."""
    try:
        data = extract_json_object(raw)
    except JsonObjectExtractionError as exc:
        logger.warning("Failed to parse model output as JSON")
        raise FindingExtractionError(str(exc)) from exc
    if "findings" not in data:
        raise FindingExtractionError("Model JSON must contain a findings array.")
    items = data["findings"]
    if not isinstance(items, list):
        raise FindingExtractionError("Model JSON must contain a findings array.")

    findings: list[Finding] = []
    rejected_count = 0
    for i, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            logger.warning("Skipping invalid finding at index %d", i)
            rejected_count += 1
            continue
        try:
            item: dict[str, Any] = raw_item
            _validate_model_owned_fields(item)
            raw_confidence = item.get("confidence")
            finding = Finding(
                id=new_finding_id(),
                target=_finding_target(item, kind),
                detected_entity_type=item.get("entity_type", "unknown"),
                reviewed_entity_type=None,
                data_subject_context=item.get("data_subject_context", "unknown"),
                label=item.get("label", ""),
                detection_confidence=(
                    float(raw_confidence) if raw_confidence is not None else None
                ),
                description=item.get("description"),
                reason=item.get("reason"),
                origin=FindingOrigin.MODEL,
                created_by=created_by,
            )
            findings.append(finding)
        except FindingExtractionError:
            raise
        except Exception:
            logger.warning("Skipping invalid finding at index %d", i)
            rejected_count += 1
            continue
    return ExtractionResult(findings=tuple(findings), rejected_count=rejected_count)
