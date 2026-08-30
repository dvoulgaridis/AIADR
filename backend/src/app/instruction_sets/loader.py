"""Securely load validated instruction sets from the project filesystem."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.domain.layer import validate_effect_support
from app.errors import ErrorCode, app_error
from app.instruction_sets.instruction_set import (
    InstructionPolicy,
    InstructionSet,
    InstructionSetManifest,
    InstructionSetSnapshot,
    PromptKey,
    PromptReference,
    ResolvedPrompt,
    reject_duplicate_members,
)
from app.sources.kinds import SourceKind


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_members)


def _resolve_member(directory: Path, reference: str, suffix: str) -> Path:
    candidate = Path(reference)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix != suffix:
        raise ValueError(f"unsafe instruction-set reference: {reference}")
    unresolved = directory / candidate
    members = [
        directory.joinpath(*candidate.parts[:index])
        for index in range(1, len(candidate.parts) + 1)
    ]
    if any(member.is_symlink() for member in members):
        raise ValueError(f"instruction-set reference uses a symlink: {reference}")
    resolved = unresolved.resolve(strict=True)
    if resolved == directory or directory not in resolved.parents:
        raise ValueError(f"instruction-set reference escapes its directory: {reference}")
    return resolved


def _validate_effects(snapshot: InstructionSetSnapshot) -> None:
    prompt_kinds = {prompt.kind for prompt in snapshot.manifest.prompts}
    default_kinds = {effect.kind for effect in snapshot.policy.defaults.effects}
    if prompt_kinds != set(PromptKey):
        raise ValueError("instruction set must define every supported prompt role")
    if default_kinds != set(SourceKind):
        raise ValueError("policy defaults must define every source kind")
    for effect in snapshot.policy.defaults.effects:
        validate_effect_support(effect.kind, effect.action, effect.effect)
    for rule in snapshot.policy.entity_rules:
        for effect in rule.effects:
            validate_effect_support(effect.kind, effect.action, effect.effect)


def _load_prompt(directory: Path, reference: PromptReference) -> ResolvedPrompt:
    try:
        path = _resolve_member(directory, reference.path, ".md")
    except FileNotFoundError as exc:
        raise app_error(
            ErrorCode.PROMPT_MISSING,
            details={"instruction_set_id": directory.name, "source_kind": reference.kind},
        ) from exc
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return ResolvedPrompt(kind=reference.kind, text=text)


def load_instruction_set_directory(
    directory: Path,
    *,
    root: Path,
) -> InstructionSet:
    """Load and validate one immediate instruction-set directory."""
    try:
        resolved_root = root.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        if directory.is_symlink() or resolved_directory.parent != resolved_root:
            raise ValueError("instruction-set directory must be an immediate non-symlink child")
        manifest_path = _resolve_member(resolved_directory, "manifest.json", ".json")
        manifest = InstructionSetManifest.model_validate(_read_json(manifest_path))
        if manifest.id != directory.name:
            raise ValueError("manifest id must match its directory name")
        if not manifest.prompts:
            raise ValueError("instruction set must declare at least one prompt")
        policy_path = _resolve_member(resolved_directory, manifest.policy, ".json")
        policy = InstructionPolicy.model_validate(_read_json(policy_path))
        prompts = tuple(
            _load_prompt(resolved_directory, reference)
            for reference in manifest.prompts
        )
        snapshot = InstructionSetSnapshot(manifest=manifest, prompts=prompts, policy=policy)
        _validate_effects(snapshot)
        return InstructionSet(snapshot=snapshot)
    except (OSError, ValueError, ValidationError, json.JSONDecodeError) as exc:
        raise app_error(
            ErrorCode.INVALID_INSTRUCTION_SET,
            details={"directory": directory.name, "reason": str(exc)},
        ) from exc
