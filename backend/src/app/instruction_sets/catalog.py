"""Discover and safely modify portable instruction-set directories."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.core.paths import instruction_sets_root
from app.errors import ErrorCode, app_error
from app.instruction_sets.instruction_set import (
    InstructionPolicy,
    InstructionSet,
    PromptKey,
    SourceEffect,
)
from app.instruction_sets.loader import load_instruction_set_directory
from app.settings.selection import (
    active_instruction_set_id,
    set_active_instruction_set_id,
)

_CATALOG_LOCK = RLock()
_PROMPT_PATHS = {kind: f"prompts/{kind.value}.md" for kind in PromptKey}
_RESERVED_PREFIXES = (".stage-", ".backup-", ".removed-")


def _require_id(instruction_set_id: str) -> str:
    if (
        not instruction_set_id
        or instruction_set_id.startswith(".")
        or Path(instruction_set_id).name != instruction_set_id
        or "/" in instruction_set_id
        or "\\" in instruction_set_id
    ):
        raise app_error(
            ErrorCode.INVALID_INSTRUCTION_SET,
            details={"instruction_set_id": instruction_set_id},
        )
    return instruction_set_id


def _root() -> Path:
    root = instruction_sets_root()
    if not root.is_dir():
        raise app_error(ErrorCode.INSTRUCTION_SET_NOT_FOUND, details={"root": str(root)})
    return root


def list_instruction_sets() -> tuple[InstructionSet, ...]:
    """Return every validated catalogue entry in deterministic ID order."""
    with _CATALOG_LOCK:
        root = _root()
        directories = (
            path
            for path in sorted(root.iterdir(), key=lambda item: item.name)
            if path.is_dir()
            and not path.name.startswith(_RESERVED_PREFIXES)
        )
        return tuple(
            load_instruction_set_directory(directory, root=root)
            for directory in directories
        )


def get_instruction_set(instruction_set_id: str) -> InstructionSet:
    """Load one validated catalogue entry by its canonical ID."""
    with _CATALOG_LOCK:
        root = _root()
        directory = root / _require_id(instruction_set_id)
        if not directory.is_dir():
            raise app_error(
                ErrorCode.INSTRUCTION_SET_NOT_FOUND,
                details={"instruction_set_id": instruction_set_id},
            )
        return load_instruction_set_directory(directory, root=root)


def get_active_instruction_set_id() -> str | None:
    """Return the selected instruction-set ID without loading its files."""
    return active_instruction_set_id()


def get_active_instruction_set() -> InstructionSet:
    """Load the instruction set selected for future analysis."""
    instruction_set_id = active_instruction_set_id()
    if instruction_set_id is None:
        raise app_error(ErrorCode.ACTIVE_INSTRUCTION_SET_NOT_SET)
    return get_instruction_set(instruction_set_id)


def activate_instruction_set(instruction_set_id: str) -> None:
    """Select one catalogue entry for future analysis."""
    get_instruction_set(instruction_set_id)
    set_active_instruction_set_id(instruction_set_id)


def _effect_document(effect: SourceEffect) -> dict[str, object]:
    return {
        "action": effect.action,
        "effect": effect.effect,
    }


def policy_document(policy: InstructionPolicy) -> dict[str, object]:
    """Return the portable JSON representation of a normalized policy."""
    defaults = policy.defaults
    default_document: dict[str, object] = {
        "privacy_category": defaults.privacy_category,
        "special_category_type": defaults.special_category_type,
        "privacy_risk": defaults.privacy_risk,
        "effects": {
            effect.kind.value: _effect_document(effect)
            for effect in defaults.effects
        },
    }
    rules: dict[str, object] = {}
    for rule in policy.entity_rules:
        document: dict[str, object] = {"display_name": rule.display_name}
        for field in (
            "description",
            "privacy_category",
            "special_category_type",
            "privacy_risk",
        ):
            value = getattr(rule, field)
            if value is not None:
                document[field] = value
        if rule.effects:
            document["effects"] = {
                effect.kind.value: _effect_document(effect)
                for effect in rule.effects
            }
        rules[rule.entity_type] = document
    return {"defaults": default_document, "entity_rules": rules}


def prompt_document(instruction_set: InstructionSet) -> dict[PromptKey, str]:
    """Return resolved prompt text keyed by its processing role."""
    return {prompt.kind: prompt.text for prompt in instruction_set.snapshot.prompts}


def _write_candidate(
    directory: Path,
    *,
    instruction_set_id: str,
    name: str,
    policy: InstructionPolicy,
    prompts: Mapping[PromptKey, str],
) -> None:
    prompt_directory = directory / "prompts"
    prompt_directory.mkdir(parents=True)
    manifest = {
        "id": instruction_set_id,
        "name": name,
        "policy": "policy.json",
        "prompts": {kind.value: _PROMPT_PATHS[kind] for kind in PromptKey},
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (directory / "policy.json").write_text(
        json.dumps(policy_document(policy), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for kind in PromptKey:
        text = prompts[kind]
        (directory / _PROMPT_PATHS[kind]).write_text(
            text.replace("\r\n", "\n").replace("\r", "\n"),
            encoding="utf-8",
        )


def _stage_candidate(
    root: Path,
    *,
    instruction_set_id: str,
    name: str,
    policy: InstructionPolicy,
    prompts: Mapping[PromptKey, str],
) -> tuple[tempfile.TemporaryDirectory[str], Path, InstructionSet]:
    stage = tempfile.TemporaryDirectory(prefix=".stage-", dir=root)
    directory = Path(stage.name) / instruction_set_id
    _write_candidate(
        directory,
        instruction_set_id=instruction_set_id,
        name=name,
        policy=policy,
        prompts=prompts,
    )
    candidate = load_instruction_set_directory(directory, root=Path(stage.name))
    return stage, directory, candidate


def create_instruction_set(
    *,
    instruction_set_id: str,
    name: str,
    policy: InstructionPolicy,
    prompts: Mapping[PromptKey, str],
) -> InstructionSet:
    """Create one validated catalogue directory."""
    with _CATALOG_LOCK:
        root = _root()
        instruction_set_id = _require_id(instruction_set_id)
        target = root / instruction_set_id
        if target.exists():
            raise app_error(
                ErrorCode.INSTRUCTION_SET_EXISTS,
                details={"instruction_set_id": instruction_set_id},
            )
        stage, directory, candidate = _stage_candidate(
            root,
            instruction_set_id=instruction_set_id,
            name=name,
            policy=policy,
            prompts=prompts,
        )
        try:
            directory.rename(target)
        finally:
            stage.cleanup()
        return candidate


def replace_instruction_set(
    instruction_set_id: str,
    *,
    name: str,
    expected_content_hash: str,
    policy: InstructionPolicy,
    prompts: Mapping[PromptKey, str],
) -> InstructionSet:
    """Replace one catalogue entry after optimistic-concurrency validation."""
    with _CATALOG_LOCK:
        root = _root()
        instruction_set_id = _require_id(instruction_set_id)
        target = root / instruction_set_id
        if not target.is_dir():
            raise app_error(
                ErrorCode.INSTRUCTION_SET_NOT_FOUND,
                details={"instruction_set_id": instruction_set_id},
            )
        current = load_instruction_set_directory(target, root=root)
        if current.content_hash != expected_content_hash:
            raise app_error(
                ErrorCode.INSTRUCTION_SET_CONFLICT,
                details={"instruction_set_id": instruction_set_id},
            )
        stage, directory, candidate = _stage_candidate(
            root,
            instruction_set_id=instruction_set_id,
            name=name,
            policy=policy,
            prompts=prompts,
        )
        try:
            backup = root / f".backup-{instruction_set_id}-{uuid4().hex}"
            target.rename(backup)
            try:
                directory.rename(target)
            except BaseException:
                backup.rename(target)
                raise
            shutil.rmtree(backup)
        finally:
            stage.cleanup()
        return candidate


def delete_instruction_set(instruction_set_id: str) -> None:
    """Remove one catalogue entry without affecting persisted session snapshots."""
    with _CATALOG_LOCK:
        root = _root()
        instruction_set_id = _require_id(instruction_set_id)
        target = root / instruction_set_id
        if not target.is_dir():
            raise app_error(
                ErrorCode.INSTRUCTION_SET_NOT_FOUND,
                details={"instruction_set_id": instruction_set_id},
            )
        load_instruction_set_directory(target, root=root)
        removed = root / f".removed-{instruction_set_id}-{uuid4().hex}"
        target.rename(removed)
        shutil.rmtree(removed)
        if active_instruction_set_id() == instruction_set_id:
            set_active_instruction_set_id(None)
