"""Format-independent replacement semantics for document text."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.domain.finding import DocumentTarget, ReviewDecision
from app.domain.layer import Layer, LayerAction, LayerEffect

_SEPARATORS = set("@.-_+/() ")
_DIGITS = set("0123456789")


def partial_mask(value: str) -> str:
    """Mask a sensitive value while preserving useful structure."""
    if "@" in value:
        local, domain = value.split("@", 1)
        if not local:
            return f"*@{domain}"
        return f"{local[0]}{'*' * max(len(local) - 1, 1)}@{domain}"
    digits = [index for index, char in enumerate(value) if char in _DIGITS]
    if len(digits) >= 5:
        keep = set(digits[-4:])
        return "".join(
            char if index in keep or char not in _DIGITS else "*"
            for index, char in enumerate(value)
        )
    masked: list[str] = []
    token_start = True
    for char in value:
        if char in _SEPARATORS:
            masked.append(char)
            token_start = True
        elif token_start:
            masked.append(char)
            token_start = False
        else:
            masked.append("*")
    return "".join(masked)


def resolve_text_replacements(layers: Sequence[Layer]) -> dict[str, str]:
    """Resolve final replacement text for renderable document layers."""
    selected = sorted(
        (
            layer
            for layer in layers
            if layer.enabled
            and layer.action is not LayerAction.PRESERVE
            and layer.finding.review_decision is ReviewDecision.CONFIRMED
            and isinstance(layer.finding.target, DocumentTarget)
        ),
        key=lambda layer: (layer.finding.id, layer.id),
    )

    counters: dict[str, int] = defaultdict(int)
    tokens: dict[tuple[str, str], str] = {}
    for layer in selected:
        if layer.effect is not LayerEffect.TOKEN_REPLACE:
            continue
        target = layer.finding.target
        assert isinstance(target, DocumentTarget)
        custom_text = layer.custom_text
        if custom_text and custom_text.strip():
            continue
        entity_type = layer.finding.effective_entity_type.upper()
        key = (entity_type, target.locator.exact_text)
        if key not in tokens:
            counters[entity_type] += 1
            tokens[key] = f"{entity_type}_{counters[entity_type]:03d}"

    replacements: dict[str, str] = {}
    for layer in selected:
        target = layer.finding.target
        assert isinstance(target, DocumentTarget)
        exact_text = target.locator.exact_text
        if layer.effect is LayerEffect.BOX:
            replacements[layer.id] = "[REDACTED]"
        elif layer.effect is LayerEffect.PARTIAL_MASK:
            replacements[layer.id] = partial_mask(exact_text)
        elif layer.effect is LayerEffect.TOKEN_REPLACE:
            custom_text = layer.custom_text
            replacements[layer.id] = (
                custom_text
                if custom_text and custom_text.strip()
                else tokens[(layer.finding.effective_entity_type.upper(), exact_text)]
            )
        else:
            raise ValueError(f"Unsupported document text effect: {layer.effect}")
    return replacements
