"""Application operations for the portable instruction-set catalogue."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from app.errors import ErrorCode, app_error
from app.instruction_sets import catalog
from app.instruction_sets.instruction_set import InstructionPolicy, InstructionSet, PromptKey


def _validated_policy(value: object) -> InstructionPolicy:
    try:
        return InstructionPolicy.model_validate(value)
    except ValidationError as exc:
        raise app_error(
            ErrorCode.INVALID_INSTRUCTION_SET,
            details={"reason": str(exc)},
        ) from exc


def _prompt_map(prompts: Mapping[str, str]) -> dict[PromptKey, str]:
    try:
        values = {PromptKey(kind): text for kind, text in prompts.items()}
        if set(values) != set(PromptKey):
            raise ValueError("every prompt role is required")
        if any(not text.strip() for text in values.values()):
            raise ValueError("prompt text must not be blank")
        return values
    except ValueError as exc:
        raise app_error(
            ErrorCode.INVALID_INSTRUCTION_SET,
            details={"reason": str(exc)},
        ) from exc


def list_available_instruction_sets() -> tuple[InstructionSet, ...]:
    """Return validated entries ordered for presentation."""
    return tuple(
        sorted(
            catalog.list_instruction_sets(),
            key=lambda item: (item.name.casefold(), item.id),
        )
    )


def get_available_instruction_set(instruction_set_id: str) -> InstructionSet:
    """Return one validated editable catalogue entry."""
    return catalog.get_instruction_set(instruction_set_id)


def activate_instruction_set(instruction_set_id: str) -> None:
    """Select one catalogue entry for future analysis."""
    catalog.activate_instruction_set(instruction_set_id)


def create_instruction_set(
    *,
    instruction_set_id: str,
    name: str,
    policy: object,
    prompts: Mapping[str, str],
) -> str:
    """Validate and create one catalogue entry."""
    created = catalog.create_instruction_set(
        instruction_set_id=instruction_set_id,
        name=name,
        policy=_validated_policy(policy),
        prompts=_prompt_map(prompts),
    )
    return created.id


def update_instruction_set(
    instruction_set_id: str,
    *,
    name: str,
    expected_content_hash: str,
    policy: object,
    prompts: Mapping[str, str],
) -> None:
    """Validate and replace one catalogue entry."""
    catalog.replace_instruction_set(
        instruction_set_id,
        name=name,
        expected_content_hash=expected_content_hash,
        policy=_validated_policy(policy),
        prompts=_prompt_map(prompts),
    )


def delete_instruction_set(instruction_set_id: str) -> None:
    """Remove one entry from the catalogue."""
    catalog.delete_instruction_set(instruction_set_id)
