"""Pydantic models for redaction and preservation layers."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, model_validator

from app.domain.finding import Finding
from app.sources.kinds import SourceKind


class LayerAction(StrEnum):
    REDACT = "redact"
    MASK = "mask"
    PSEUDONYMIZE = "pseudonymize"
    PRESERVE = "preserve"


class LayerEffect(StrEnum):
    BOX = "box"
    BLUR = "blur"
    PIXELATE = "pixelate"
    PARTIAL_MASK = "partial_mask"
    TOKEN_REPLACE = "token_replace"
    BLEEP = "bleep"
    MUTE = "mute"
    NONE = "none"


class EffectSource(StrEnum):
    POLICY = "policy"
    REVIEWER = "reviewer"

SUPPORTED_EFFECTS_BY_KIND_AND_ACTION: Final[
    dict[SourceKind, dict[LayerAction, tuple[LayerEffect, ...]]]
] = {
    SourceKind.IMAGE: {
        LayerAction.REDACT: (LayerEffect.BOX, LayerEffect.BLUR, LayerEffect.PIXELATE),
        LayerAction.PRESERVE: (LayerEffect.NONE,),
    },
    SourceKind.DOCUMENT: {
        LayerAction.REDACT: (LayerEffect.BOX,),
        LayerAction.MASK: (LayerEffect.PARTIAL_MASK,),
        LayerAction.PSEUDONYMIZE: (LayerEffect.TOKEN_REPLACE,),
        LayerAction.PRESERVE: (LayerEffect.NONE,),
    },
    SourceKind.AUDIO: {
        LayerAction.REDACT: (LayerEffect.MUTE, LayerEffect.BLEEP),
        LayerAction.PRESERVE: (LayerEffect.NONE,),
    },
}


def is_effect_supported(kind: SourceKind, action: LayerAction, effect: LayerEffect) -> bool:
    """Return whether one source/action/effect combination is renderable."""
    return effect in SUPPORTED_EFFECTS_BY_KIND_AND_ACTION.get(kind, {}).get(action, ())


def validate_effect_support(kind: SourceKind, action: LayerAction, effect: LayerEffect) -> None:
    """Raise a domain validation error for an unsupported combination."""
    if not is_effect_supported(kind, action, effect):
        raise ValueError(f"{action} + {effect} is not supported for {kind}")


class Layer(BaseModel):
    """Immutable redaction-effect configuration tied to one finding."""

    id: str
    finding: Finding
    action: LayerAction = LayerAction.REDACT
    effect: LayerEffect = LayerEffect.BOX
    effect_source: EffectSource
    enabled: bool = True

    fill_color: str = "#000000"
    custom_text: str | None = None
    note: str | None = None

    @property
    def kind(self) -> SourceKind:
        return self.finding.target.kind

    @model_validator(mode="after")
    def preserve_uses_none(self) -> Layer:
        if not is_effect_supported(self.kind, self.action, self.effect):
            raise ValueError("unsupported source-kind/action/effect combination")
        if self.action is LayerAction.PRESERVE and self.effect is not LayerEffect.NONE:
            raise ValueError("preserve action must use none effect")
        if (
            self.action is LayerAction.PSEUDONYMIZE
            and self.effect is not LayerEffect.TOKEN_REPLACE
        ):
            raise ValueError("pseudonymize action must use token_replace effect")
        if self.custom_text and (
            self.action is not LayerAction.PSEUDONYMIZE
            or self.effect is not LayerEffect.TOKEN_REPLACE
        ):
            raise ValueError("custom_text is only valid for pseudonymize + token_replace")
        return self

    model_config = {"frozen": True}
