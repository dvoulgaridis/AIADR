"""Pure mapping from findings and instruction policy to review layers."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.ids import new_layer_id
from app.domain.finding import Finding
from app.domain.layer import (
    EffectSource,
    Layer,
    LayerAction,
    LayerEffect,
    validate_effect_support,
)
from app.instruction_sets.instruction_set import InstructionPolicy, SourceEffect


@dataclass(frozen=True, slots=True)
class _PolicyResolution:
    finding: Finding
    source_effect: SourceEffect


def _value(rule: object | None, name: str, default: object) -> object:
    value = getattr(rule, name, None) if rule is not None else None
    return default if value is None else value


def _resolve_policy(finding: Finding, policy: InstructionPolicy) -> _PolicyResolution:
    defaults = policy.defaults
    rule = policy.rule_for(finding.effective_entity_type)
    classified = finding.model_copy(
        update={
            "privacy_category": _value(rule, "privacy_category", defaults.privacy_category),
            "special_category_type": _value(
                rule,
                "special_category_type",
                defaults.special_category_type,
            ),
            "privacy_risk": _value(rule, "privacy_risk", defaults.privacy_risk),
        }
    )
    source_effect = (rule.effect_for(finding.kind) if rule is not None else None) or (
        defaults.effect_for(finding.kind)
    )
    validate_effect_support(finding.kind, source_effect.action, source_effect.effect)
    return _PolicyResolution(finding=classified, source_effect=source_effect)


def map_finding_to_layer(finding: Finding, policy: InstructionPolicy) -> Layer:
    """Create one policy-sourced layer with a new identity."""
    resolved = _resolve_policy(finding, policy)
    return Layer(
        id=new_layer_id(),
        finding=resolved.finding,
        action=resolved.source_effect.action,
        effect=resolved.source_effect.effect,
        effect_source=EffectSource.POLICY,
    )


def reclassify_layer(layer: Layer, finding: Finding, policy: InstructionPolicy) -> Layer:
    """Reapply classification while retaining layer identity and reviewer effects."""
    resolved = _resolve_policy(finding, policy)
    updates: dict[str, object] = {"finding": resolved.finding}
    if layer.effect_source is EffectSource.POLICY:
        updates.update(
            action=resolved.source_effect.action,
            effect=resolved.source_effect.effect,
            custom_text=(
                layer.custom_text
                if resolved.source_effect.action is LayerAction.PSEUDONYMIZE
                and resolved.source_effect.effect is LayerEffect.TOKEN_REPLACE
                else None
            ),
        )
    else:
        validate_effect_support(finding.kind, layer.action, layer.effect)
    candidate = layer.model_copy(update=updates)
    return Layer.model_validate(candidate.model_dump(exclude_computed_fields=True))
