"""In-memory task registry for active analysis tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, TypeAlias


@dataclass(slots=True)
class TaskEntry:
    """One admitted task and its public analysis activity."""

    task: asyncio.Task[None]
    analysis_active: bool = True


_task_registry: dict[str, TaskEntry] = {}
TaskFactory: TypeAlias = Callable[[], Coroutine[Any, Any, None]]
logger = logging.getLogger(__name__)


def create_task(
    session_id: str,
    factory: TaskFactory,
) -> asyncio.Task[None] | None:
    """Atomically admit one task per session in this event-loop process."""
    current = _task_registry.get(session_id)
    if current is not None and not current.task.done():
        return None
    task = asyncio.create_task(factory())
    _task_registry[session_id] = TaskEntry(task=task)
    task.add_done_callback(lambda completed: remove_task(session_id, completed))
    return task


def has_task(session_id: str) -> bool:
    """Return whether an unfinished task owns admission for the session."""
    entry = _task_registry.get(session_id)
    return entry is not None and not entry.task.done()


def is_active(session_id: str) -> bool:
    """Return whether this process is analyzing the session."""
    entry = _task_registry.get(session_id)
    return (
        entry is not None
        and entry.analysis_active
        and not entry.task.done()
    )


def mark_finishing(session_id: str) -> None:
    """Mark the task publicly inactive while retaining admission until exit."""
    entry = _task_registry.get(session_id)
    current = asyncio.current_task()
    if entry is None or entry.task is not current:
        raise RuntimeError(
            "Only the registered analysis task may mark itself finishing."
        )
    entry.analysis_active = False


def cancel_task(session_id: str) -> bool:
    """Cancel an active task, excluding tasks already finishing."""
    entry = _task_registry.get(session_id)
    if (
        entry is None
        or not entry.analysis_active
        or entry.task.done()
    ):
        return False
    entry.task.cancel()
    return True


def remove_task(session_id: str, task: asyncio.Task[Any]) -> None:
    """Remove only the task currently registered under the session."""
    entry = _task_registry.get(session_id)
    if entry is not None and entry.task is task:
        _task_registry.pop(session_id, None)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error(
            "Background task failed session_id=%s",
            session_id,
        )
