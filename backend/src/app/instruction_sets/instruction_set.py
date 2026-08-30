"""Deeply immutable instruction-set contracts and canonical snapshots."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.finding import PrivacyCategory, PrivacyRisk, SpecialCategoryType
from app.domain.layer import LayerAction, LayerEffect
from app.sources.kinds import SourceKind

_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ENTITY_TYPE_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class PromptKey(StrEnum):
    TEXT = "text"
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"


class SourceEffect(BaseModel):
    kind: SourceKind
    action: LayerAction
    effect: LayerEffect

    model_config = {"extra": "forbid", "frozen": True}


def _effect_entries(value: object) -> object:
    if not isinstance(value, dict):
        return value
    return tuple({"kind": kind, **entry} for kind, entry in sorted(value.items()))


class PolicyDefaults(BaseModel):
    privacy_category: PrivacyCategory
    special_category_type: SpecialCategoryType
    privacy_risk: PrivacyRisk
    effects: tuple[SourceEffect, ...]

    model_config = {"extra": "forbid", "frozen": True}

    @field_validator("effects", mode="before")
    @classmethod
    def normalize_effects(cls, value: object) -> object:
        return _effect_entries(value)

    @field_validator("effects")
    @classmethod
    def validate_effects(cls, effects: tuple[SourceEffect, ...]) -> tuple[SourceEffect, ...]:
        kinds = [effect.kind for effect in effects]
        if not kinds or len(kinds) != len(set(kinds)):
            raise ValueError("default effects require unique source kinds")
        return tuple(sorted(effects, key=lambda effect: effect.kind))

    def effect_for(self, kind: SourceKind) -> SourceEffect:
        return next(effect for effect in self.effects if effect.kind == kind)


class PolicyRule(BaseModel):
    entity_type: str
    display_name: str = Field(min_length=1)
    privacy_category: PrivacyCategory | None = None
    special_category_type: SpecialCategoryType | None = None
    privacy_risk: PrivacyRisk | None = None
    effects: tuple[SourceEffect, ...] = ()
    description: str | None = None

    model_config = {"extra": "forbid", "frozen": True}

    @field_validator("effects", mode="before")
    @classmethod
    def normalize_effects(cls, value: object) -> object:
        return _effect_entries(value)

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, value: str) -> str:
        if not _ENTITY_TYPE_PATTERN.fullmatch(value):
            raise ValueError("entity type must be lowercase snake_case")
        return value

    @field_validator("effects")
    @classmethod
    def validate_effects(cls, effects: tuple[SourceEffect, ...]) -> tuple[SourceEffect, ...]:
        kinds = [effect.kind for effect in effects]
        if len(kinds) != len(set(kinds)):
            raise ValueError("rule effects require unique source kinds")
        return tuple(sorted(effects, key=lambda effect: effect.kind))

    def effect_for(self, kind: SourceKind) -> SourceEffect | None:
        return next((effect for effect in self.effects if effect.kind == kind), None)


class InstructionPolicy(BaseModel):
    defaults: PolicyDefaults
    entity_rules: tuple[PolicyRule, ...]

    model_config = {"extra": "forbid", "frozen": True}

    @field_validator("entity_rules", mode="before")
    @classmethod
    def normalize_rules(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return tuple({"entity_type": key, **rule} for key, rule in sorted(value.items()))

    @field_validator("entity_rules")
    @classmethod
    def validate_rules(cls, rules: tuple[PolicyRule, ...]) -> tuple[PolicyRule, ...]:
        entity_types = [rule.entity_type for rule in rules]
        if not entity_types or len(entity_types) != len(set(entity_types)):
            raise ValueError("policy requires unique entity types")
        return tuple(sorted(rules, key=lambda rule: rule.entity_type))

    def rule_for(self, entity_type: str) -> PolicyRule | None:
        return next((rule for rule in self.entity_rules if rule.entity_type == entity_type), None)


class PromptReference(BaseModel):
    kind: PromptKey
    path: str

    model_config = {"extra": "forbid", "frozen": True}


class ResolvedPrompt(BaseModel):
    kind: PromptKey
    text: str = Field(min_length=1)

    model_config = {"extra": "forbid", "frozen": True}

    @field_validator("text")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("resolved prompt text must not be blank")
        return value


class InstructionSetManifest(BaseModel):
    id: str
    name: str = Field(min_length=1)
    policy: str
    prompts: tuple[PromptReference, ...]

    model_config = {"extra": "forbid", "frozen": True}

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("instruction-set id must be lowercase kebab-case")
        return value

    @field_validator("prompts", mode="before")
    @classmethod
    def normalize_prompts(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return tuple({"kind": kind, "path": path} for kind, path in sorted(value.items()))

    @field_validator("prompts")
    @classmethod
    def validate_prompts(cls, prompts: tuple[PromptReference, ...]) -> tuple[PromptReference, ...]:
        kinds = [prompt.kind for prompt in prompts]
        if not kinds or len(kinds) != len(set(kinds)):
            raise ValueError("manifest prompts require unique source kinds")
        return tuple(sorted(prompts, key=lambda prompt: prompt.kind))


class InstructionSetSnapshot(BaseModel):
    manifest: InstructionSetManifest
    prompts: tuple[ResolvedPrompt, ...]
    policy: InstructionPolicy

    model_config = {"extra": "forbid", "frozen": True}

    @field_validator("prompts")
    @classmethod
    def validate_prompts(cls, prompts: tuple[ResolvedPrompt, ...]) -> tuple[ResolvedPrompt, ...]:
        kinds = [prompt.kind for prompt in prompts]
        if not kinds or len(kinds) != len(set(kinds)):
            raise ValueError("resolved prompts require unique source kinds")
        return tuple(sorted(prompts, key=lambda prompt: prompt.kind))

    @model_validator(mode="after")
    def require_declared_prompts(self) -> InstructionSetSnapshot:
        declared = {prompt.kind for prompt in self.manifest.prompts}
        resolved = {prompt.kind for prompt in self.prompts}
        if declared != resolved:
            raise ValueError("resolved prompt kinds must equal manifest prompt kinds")
        return self

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class InstructionSet(BaseModel):
    snapshot: InstructionSetSnapshot

    model_config = {"extra": "forbid", "frozen": True}

    @property
    def snapshot_bytes(self) -> bytes:
        return self.snapshot.canonical_bytes()

    @property
    def id(self) -> str:
        return self.snapshot.manifest.id

    @property
    def name(self) -> str:
        return self.snapshot.manifest.name

    @property
    def policy(self) -> InstructionPolicy:
        return self.snapshot.policy

    @property
    def content_hash(self) -> str:
        return sha256(self.snapshot_bytes).hexdigest()

    def prompt_for(self, kind: PromptKey) -> str:
        try:
            return next(prompt.text for prompt in self.snapshot.prompts if prompt.kind == kind)
        except StopIteration as exc:
            raise KeyError(kind) from exc


def instruction_set_from_snapshot(
    snapshot_bytes: bytes,
    *,
    expected_id: str,
    expected_hash: str,
) -> InstructionSet:
    """Restore and verify one persisted canonical snapshot."""
    if sha256(snapshot_bytes).hexdigest() != expected_hash:
        raise ValueError("snapshot hash does not match")
    snapshot = InstructionSetSnapshot.model_validate_json(snapshot_bytes)
    if snapshot.canonical_bytes() != snapshot_bytes:
        raise ValueError("snapshot bytes are not canonical")
    instruction_set = InstructionSet(snapshot=snapshot)
    if instruction_set.id != expected_id:
        raise ValueError("snapshot identity does not match")
    return instruction_set


def reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result
