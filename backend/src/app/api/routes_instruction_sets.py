"""HTTP routes for portable instruction-set catalogue management."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.contracts import (
    InstructionSetCreateRequest,
    InstructionSetDefinition,
    InstructionSetPrompts,
    InstructionSetsResponse,
    InstructionSetSummary,
    InstructionSetUpdateRequest,
)
from app.instruction_sets.catalog import (
    get_active_instruction_set_id,
    policy_document,
    prompt_document,
)
from app.instruction_sets.instruction_set import InstructionSet, PromptKey
from app.operations import instruction_sets as operations

router = APIRouter(tags=["instruction-sets"])


def _summary(instruction_set: InstructionSet) -> InstructionSetSummary:
    return InstructionSetSummary(
        id=instruction_set.id,
        name=instruction_set.name,
        content_hash=instruction_set.content_hash,
    )


def _definition(instruction_set: InstructionSet) -> InstructionSetDefinition:
    prompts = prompt_document(instruction_set)
    return InstructionSetDefinition(
        id=instruction_set.id,
        name=instruction_set.name,
        content_hash=instruction_set.content_hash,
        policy=policy_document(instruction_set.policy),
        prompts=InstructionSetPrompts(
            text=prompts[PromptKey.TEXT],
            document=prompts[PromptKey.DOCUMENT],
            image=prompts[PromptKey.IMAGE],
            audio=prompts[PromptKey.AUDIO],
        ),
    )


@router.get("/instruction-sets")
async def list_instruction_sets() -> InstructionSetsResponse:
    """List instruction sets available to future sessions."""
    return InstructionSetsResponse(
        items=[_summary(item) for item in operations.list_available_instruction_sets()],
        active_instruction_set_id=get_active_instruction_set_id(),
    )


@router.get("/instruction-sets/{instruction_set_id}")
async def get_instruction_set(instruction_set_id: str) -> InstructionSetDefinition:
    """Return one editable instruction-set definition."""
    return _definition(operations.get_available_instruction_set(instruction_set_id))


@router.post("/instruction-sets", status_code=status.HTTP_201_CREATED)
async def request_create_instruction_set(request: InstructionSetCreateRequest) -> str:
    """Create a validated portable instruction set."""
    return operations.create_instruction_set(
        instruction_set_id=request.id,
        name=request.name,
        policy=request.policy,
        prompts=request.prompts.model_dump(),
    )


@router.put(
    "/instruction-sets/{instruction_set_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_update_instruction_set(
    instruction_set_id: str,
    request: InstructionSetUpdateRequest,
) -> Response:
    """Replace a catalogue entry after content-hash validation."""
    operations.update_instruction_set(
        instruction_set_id,
        name=request.name,
        expected_content_hash=request.expected_content_hash,
        policy=request.policy,
        prompts=request.prompts.model_dump(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/instruction-sets/{instruction_set_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_delete_instruction_set(instruction_set_id: str) -> Response:
    """Remove a catalogue entry without changing existing session snapshots."""
    operations.delete_instruction_set(instruction_set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/instruction-sets/{instruction_set_id}/active",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def request_activate_instruction_set(instruction_set_id: str) -> Response:
    """Select an instruction set for future analysis."""
    operations.activate_instruction_set(instruction_set_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
